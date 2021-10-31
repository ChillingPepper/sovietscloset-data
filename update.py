import json
import re
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import eventlet
import requests
from eventlet.green.urllib.request import urlopen
from eventlet.greenthread import sleep

from sovietscloset import SovietsCloset


def js_to_json(code, vars={}):
    # vars is a dict of var, val pairs to substitute
    COMMENT_RE = r"/\*(?:(?!\*/).)*?\*/|//[^\n]*\n"
    SKIP_RE = r"\s*(?:{comment})?\s*".format(comment=COMMENT_RE)
    INTEGER_TABLE = (
        (r"(?s)^(0[xX][0-9a-fA-F]+){skip}:?$".format(skip=SKIP_RE), 16),
        (r"(?s)^(0+[0-7]+){skip}:?$".format(skip=SKIP_RE), 8),
    )

    def fix_kv(m):
        v = m.group(0)
        if v in ("true", "false", "null"):
            return v
        elif v in ("undefined", "void 0"):
            return "null"
        elif v.startswith("/*") or v.startswith("//") or v.startswith("!") or v == ",":
            return ""

        if v[0] in ("'", '"'):
            v = re.sub(
                r'(?s)\\.|"',
                lambda m: {
                    '"': '\\"',
                    "\\'": "'",
                    "\\\n": "",
                    "\\x": "\\u00",
                }.get(m.group(0), m.group(0)),
                v[1:-1],
            )
        else:
            for regex, base in INTEGER_TABLE:
                im = re.match(regex, v)
                if im:
                    i = int(im.group(1), base)
                    return f'"{i}":' if v.endswith(":") else str(i)

            if v in vars:
                return vars[v]

        return f'"{v}"'

    return re.sub(
        r"""(?sx)
            "(?:[^"\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^"\\]*"|
            '(?:[^'\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^'\\]*'|
            {comment}|,(?={skip}[\]}}])|
            void\s0|(?:(?<![0-9])[eE]|[a-df-zA-DF-Z_$])[.a-zA-Z_$0-9]*|
            \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:{skip}:)?|
            [0-9]+(?={skip}:)|
            !+
        """.format(
            comment=COMMENT_RE, skip=SKIP_RE
        ),
        fix_kv,
        code,
    )


MEDIADELIVERY_REFERER = {"Referer": "https://iframe.mediadelivery.net/"}


def log(source, message):
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{timestamp}Z] [{source}] {message}")


def download(url, headers={}, progress=None):
    if not progress:
        log("download", url)
    else:
        index = progress[0]
        max_ = progress[1]
        index_justified = str(index).rjust(len(str(max_)), "0")
        log("download", f"{index_justified}/{max_} {url}")
    # TODO handle errors
    return requests.get(url, headers=headers).text


def parse_nuxt_jsonp(nuxt_jsonp):
    NUXT_JSONP_RE = r"__NUXT_JSONP__\(.*?\(function\((?P<arg_keys>.*?)\)\{return\s(?P<js>\{.*?\})\}\((?P<arg_vals>.*?)\)"
    match = next(re.finditer(NUXT_JSONP_RE, nuxt_jsonp))
    arg_keys = match.group("arg_keys").split(",")
    arg_vals = match.group("arg_vals").split(",")
    js = match.group("js")

    args = {key: val for key, val in zip(arg_keys, arg_vals)}

    for key, val in args.items():
        if val in ("undefined", "void 0"):
            args[key] = "null"

    return json.loads(js_to_json(js, args))["data"][0]


def get_global_vars():
    video_html = download("https://sovietscloset.com/video/1234")
    video_match = next(
        re.finditer(
            r"https:\/\/iframe\.mediadelivery\.net\/embed\/(?P<video_library_id>[0-9]+)\/(?P<video_id>[0-9a-f-]+)",
            video_html,
        )
    )

    static_assets_base = re.findall(r"staticAssetsBase:\"(.*?)\"", video_html)[0]
    static_assets_base = f"https://sovietscloset.com{static_assets_base}"

    video_library_id = video_match.group("video_library_id")
    video_id = video_match.group("video_id")
    embed_url = video_match[0]

    embed_html = download(embed_url, headers=MEDIADELIVERY_REFERER)
    embed_match = next(
        re.finditer(r"https:\/\/(?P<pull_zone>.*)\.b-cdn\.net\/%s\/" % video_id, embed_html)
    )
    pull_zone = embed_match.group("pull_zone")

    # Path("debug.video.html").write_text(video_html)
    # Path("debug.embed.html").write_text(embed_html)

    return {
        "staticAssetsBase": static_assets_base,
        "staticAssetsTimestamp": int(static_assets_base.split("/")[-1]),
        "pullZone": pull_zone.split("/")[-1],
        "videoLibraryId": video_library_id,
    }


def update_raw_data():
    log("update_raw_data", "start")

    global_vars = get_global_vars()
    json.dump(global_vars, open("raw/global.json", "w"), indent=2)

    base_url = global_vars["staticAssetsBase"]
    static_assets_timestamp = global_vars["staticAssetsTimestamp"]

    log("update_raw_data", f"{static_assets_timestamp=}")

    if static_assets_timestamp == int(Path("raw/static_assets_timestamp").read_text()):
        log("update_raw_data", "static_assets_timestamp unchanged, aborting")
        return
    log("update_raw_data", "static_assets_timestamp changed, updating")

    log("update_raw_data", "updating index data")
    sovietscloset = parse_nuxt_jsonp(download(f"{base_url}/payload.js"))["games"]
    json.dump(sovietscloset, open("raw/index.json", "w"), indent=2)

    log("update_raw_data", "updating video data")

    def update_raw_video(video_id):
        stream_details_url = f"{base_url}/video/{video_id}/payload.js"
        # log("update_raw_video", f"downloading {stream_details_url}")
        stream_details_jsonp = urlopen(stream_details_url).read().decode("utf-8")
        sleep()
        stream_details = parse_nuxt_jsonp(stream_details_jsonp)["stream"]
        sleep()
        json.dump(stream_details, open(f"raw/video/{video_id}.json", "w"), indent=2)

    pool = eventlet.GreenPool(32)
    video_ids = [
        stream["id"]
        for game in sovietscloset
        for subcategory in game["subcategories"]
        for stream in subcategory["streams"]
    ]

    start_time = time.time()
    progress_index = 0
    progress_max = str(len(video_ids))
    for _ in pool.imap(update_raw_video, video_ids):
        progress_index += 1
        progress_index_rjust = str(progress_index).rjust(len(progress_max), "0")
        progress = f"{progress_index_rjust}/{progress_max}"
        log("update_raw_data", f"updated video {progress}")

    log("update_raw_data", f"updating video details took {time.time() - start_time:.2f} seconds")

    log("update_raw_data", "caching static_assets_timestamp")
    Path("raw/static_assets_timestamp").write_text(str(static_assets_timestamp))

    log("update_raw_data", "update done")


def combine_data():
    log("combine_data", "start")
    sovietscloset = dict()

    global_vars = json.load(open("raw/global.json"))
    sovietscloset["timestamp"] = global_vars["staticAssetsTimestamp"]
    sovietscloset["bunnyCdn"] = dict()
    for key in ["pullZone", "videoLibraryId"]:
        sovietscloset["bunnyCdn"][key] = global_vars[key]

    raw_index = json.load(open("raw/index.json"))
    sovietscloset["games"] = list()
    for index_game in raw_index:
        game = dict()
        game["title"] = index_game["name"]
        game["url"] = f"https://sovietscloset.com/{index_game['slug']}"
        for key in ["name", "slug", "enabled", "recentlyUpdated"]:
            game[key] = index_game[key]

        game["playlists"] = list()
        for index_subcategory in index_game["subcategories"]:
            playlist = dict()
            playlist["title"] = game["title"]
            playlist["url"] = game["url"]
            if index_subcategory["name"] != "Misc":
                playlist["title"] += f" - {index_subcategory['name']}"
                playlist["url"] += f"/{index_subcategory['slug']}"
            for key in ["name", "slug", "enabled", "recentlyUpdated"]:
                playlist[key] = index_subcategory[key]

            playlist["videos"] = list()
            for index_video in index_subcategory["streams"]:
                raw_video = json.load(open(f"raw/video/{index_video['id']}.json"))
                combined_video = {**index_video, **raw_video}

                video = dict()
                video["title"] = f"{playlist['title']} #{combined_video['number']}"
                video["url"] = f"https://sovietscloset.com/video/{combined_video['id']}"
                for key in ["id", "date", "number", "bunnyId", "new"]:
                    video[key] = combined_video[key]

                playlist["videos"].append(video)
            game["playlists"].append(playlist)
        sovietscloset["games"].append(game)

    json.dump(sovietscloset, open("sovietscloset.json", "w"), indent=2)
    log("combine_data", "written to sovietscloset.json")


def update_oopsies():
    log("update_oopsies", "start")
    missing_bunnycdn: List[SovietsCloset.Video] = list()
    missing_completely: List[(SovietsCloset.Playlist, int, int)] = list()

    sorting_date: List[SovietsCloset.Video] = list()
    sorting_number: List[SovietsCloset.Video] = list()

    dupes_date: Dict[str, List[SovietsCloset.Video]] = dict()
    dupes_number: Dict[int, List[SovietsCloset.Video]] = dict()
    dupes_bunnycdn: Dict[str, List[SovietsCloset.Video]] = dict()

    sovietscloset = SovietsCloset()
    for game in sovietscloset:
        for playlist in game:
            # missing bunnycdn
            for video in playlist:
                if not video.bunnyId:
                    missing_bunnycdn.append(video)

            # missing completely
            last_video_number = 0
            for video in playlist:
                if video.number != last_video_number + 1:
                    missing_completely.append((playlist, last_video_number + 1, video.number - 1))
                last_video_number = video.number

            # sorting
            for i, video in enumerate(playlist):
                if i > 0:
                    last_video = playlist[i - 1]

                    # sorting by date
                    if video.date < last_video.date:
                        sorting_date.append(video)

                    # sorting by number
                    if video.number < last_video.number:
                        sorting_number.append(video)

            # dupes
            dates: Dict[str, List[SovietsCloset.Video]] = dict()
            numbers: Dict[int, List[SovietsCloset.Video]] = dict()
            bunnycdn: Dict[str, List[SovietsCloset.Video]] = dict()

            for video in playlist:
                for key_name, temp_dict, dupes_dict in [
                    ("date", dates, dupes_date),
                    ("number", numbers, dupes_number),
                    ("bunnyId", bunnycdn, dupes_bunnycdn),
                ]:
                    key = video.__getattribute__(key_name)
                    if key not in temp_dict:
                        temp_dict[key] = list()
                    temp_dict[key].append(video)

                    if len(temp_dict[key]) > 1:
                        if key not in dupes_dict:
                            dupes_dict[key] = list()
                        dupes_dict[key] = temp_dict[key]

    oopsies_md = "# Oopsies\n\n"
    oopsies_md += f"Last updated at {sovietscloset.timestamp.isoformat(timespec='seconds')}Z.\n\n"

    # missing
    oopsies_md += "## Missing\n\n"

    oopsies_md += "### Missing from BunnyCDN\n\n"
    oopsies_md += "This list includes all videos that used to be available on Vimeo but are not available on BunnyCDN yet.\n\n"

    if len(missing_bunnycdn):
        for video in missing_bunnycdn:
            oopsies_md += f"- [{video.title}](https://sovietscloset.com/video/{video.id})\n"
    else:
        oopsies_md += "All videos are on BunnyCDN. :tada:\n"
    oopsies_md += "\n"

    oopsies_md += "### Missing from Playlist\n\n"
    oopsies_md += "This list includes videos that are missing from playlists.\n"
    oopsies_md += "Missing videos are only detected if they are followed by a video that is already available.\n\n"

    if len(missing_completely):
        last_title = None
        for playlist, start, stop in missing_completely:
            if playlist.title != last_title:
                oopsies_md += f"- [{playlist.title}]({playlist.url})\n"
                last_title = playlist.title

            for i in range(start, stop + 1):
                oopsies_md += f"  - {playlist.title} #{i}\n"
    else:
        oopsies_md += "All playlists are continuous. :tada:\n"
    oopsies_md += "\n"

    # sorting
    oopsies_md += "## Sorting\n\n"

    oopsies_md += "### Sorting by Date\n\n"
    oopsies_md += "This list includes all videos that have a date that is earlier than the date of the previous video.\n\n"
    if len(sorting_date):
        for video in sorting_date:
            oopsies_md += f"- [{video.title}](https://sovietscloset.com/video/{video.id})\n"
    else:
        oopsies_md += "All videos are sorted by date. :tada:\n"
    oopsies_md += "\n"

    oopsies_md += "### Sorting by Number\n\n"
    oopsies_md += "This list includes all videos that have a number that is lower than the number of the previous video.\n\n"
    if len(sorting_number):
        for video in sorting_number:
            oopsies_md += f"- [{video.title}](https://sovietscloset.com/video/{video.id})\n"
    else:
        oopsies_md += "All videos are sorted by number. :tada:\n"
    oopsies_md += "\n"

    # dupes
    oopsies_md += "## Dupes\n"

    for name, dupes in [
        ("date", dupes_date),
        ("number", dupes_number),
        ("BunnyCDN ID", dupes_bunnycdn),
    ]:
        capitalized_name = name[0].upper() + name[1:]
        oopsies_md += "\n"
        oopsies_md += f"### Dupes by {capitalized_name}\n\n"
        oopsies_md += f"This list includes all videos that have the same {name}.\n\n"

        if dupes:
            for key, videos in dupes.items():
                oopsies_md += f"- {capitalized_name}: {key}\n"
                for video in videos:
                    oopsies_md += f"  - [{video.title}](https://sovietscloset.com/video/{video.id}) (id: {video.id})\n"
        else:
            oopsies_md += f"All videos have a unique {name}. :tada:\n"

    Path("OOPSIES.md").write_text(oopsies_md)
    log("update_oopsies", "written to OOPSIES.md")


class ChangeType(Enum):
    ADD = 1
    DELETE = 2
    MODIFY = 3

    def __str__(self):
        if self == ChangeType.ADD:
            return "Added"
        elif self == ChangeType.DELETE:
            return "Deleted"
        elif self == ChangeType.MODIFY:
            return "Modified"
        else:
            raise RuntimeError()


def update_changelog(old_sovietscloset: SovietsCloset, new_sovietscloset: SovietsCloset):
    log("update_changelog", "start")

    changelog_timestamp = new_sovietscloset.timestamp.isoformat(timespec="seconds")

    changelog_games: List[(ChangeType, SovietsCloset.Game, SovietsCloset.Game)] = list()
    changelog_playlists: List[
        (ChangeType, SovietsCloset.Playlist, SovietsCloset.Playlist)
    ] = list()
    changelog_videos: List[(ChangeType, SovietsCloset.Video, SovietsCloset.Video)] = list()

    def find_element(elements, comparison_element, key):
        return next(
            (
                element
                for element in elements
                if element.__getattribute__(key) == comparison_element.__getattribute__(key)
            ),
            None,
        )

    # find added games
    for new_game in new_sovietscloset:
        is_modified_game = False

        found_old_game: Optional[SovietsCloset.Game] = find_element(
            old_sovietscloset.games, new_game, "name"
        )
        if not found_old_game:
            # added game with new playlists and new videos
            changelog_games.append((ChangeType.ADD, new_game, new_game))
            for new_playlist in new_game:
                changelog_playlists.append((ChangeType.ADD, new_playlist, new_playlist))
                for new_video in new_playlist:
                    changelog_videos.append((ChangeType.ADD, new_video, new_video))
        else:

            # find added playlists
            for new_playlist in new_game:
                is_modified_playlist = False

                found_old_playlist: Optional[SovietsCloset.Playlist] = find_element(
                    found_old_game.playlists, new_playlist, "name"
                )
                if not found_old_playlist:
                    # added playlist with added videos in modified game
                    is_modified_game = True
                    changelog_playlists.append((ChangeType.ADD, new_playlist, new_playlist))
                    for new_video in new_playlist:
                        changelog_videos.append((ChangeType.ADD, new_video, new_video))
                else:

                    # find added videos
                    for new_video in new_playlist:
                        found_old_video: Optional[SovietsCloset.Game] = find_element(
                            found_old_playlist.videos, new_video, "id"
                        )
                        if not found_old_video:
                            # added video in modified playlist in modified game
                            is_modified_game = True
                            is_modified_playlist = True
                            changelog_videos.append((ChangeType.ADD, new_video, new_video))

                if is_modified_playlist:
                    playlist_tuple = (ChangeType.MODIFY, found_old_playlist, new_playlist)
                    if playlist_tuple not in changelog_playlists:
                        changelog_playlists.append(playlist_tuple)

        if is_modified_game:
            game_tuple = (ChangeType.MODIFY, found_old_game, new_game)
            if game_tuple not in changelog_games:
                changelog_games.append(game_tuple)

    # find deleted and modified games
    for old_game in old_sovietscloset:
        is_modified_game = False

        # find deleted games
        found_new_game: Optional[SovietsCloset.Game] = find_element(
            new_sovietscloset.games, old_game, "name"
        )
        if not found_new_game:
            # deleted game with deleted playlists and deleted videos
            changelog_games.append((ChangeType.DELETE, old_game, old_game))
            for old_playlist in old_game:
                changelog_playlists.append((ChangeType.DELETE, old_playlist, old_playlist))
                for old_video in old_playlist:
                    changelog_videos.append((ChangeType.DELETE, old_video, old_video))
        else:

            # find modified games
            if found_new_game != old_game:
                is_modified_game = True

            # find deleted and modified playlists
            for old_playlist in old_game:
                is_modified_playlist = False

                # find deleted playlists
                found_new_playlist: Optional[SovietsCloset.Playlist] = find_element(
                    found_new_game.playlists, old_playlist, "name"
                )
                if not found_new_playlist:
                    # deleted playlist with deleted videos in modified game
                    is_modified_game = True
                    changelog_playlists.append((ChangeType.DELETE, old_playlist, old_playlist))
                    for old_video in old_playlist:
                        changelog_videos.append((ChangeType.DELETE, old_video, old_video))

                else:

                    # find modified playlists
                    if found_new_playlist != old_playlist:
                        is_modified_game = True
                        is_modified_playlist = True

                    # find deleted and modified videos
                    for old_video in old_playlist:

                        # find deleted videos
                        found_new_video: Optional[SovietsCloset.Video] = find_element(
                            found_new_playlist.videos, old_video, "id"
                        )
                        if not found_new_video:
                            # deleted video in modified playlist in modified game
                            is_modified_game = True
                            is_modified_playlist = True
                            changelog_videos.append((ChangeType.DELETE, old_video, old_video))

                        else:
                            if found_new_video != old_video:
                                # modified video in modified playlist in modified game
                                is_modified_game = True
                                is_modified_playlist = True
                                changelog_videos.append(
                                    (ChangeType.MODIFY, old_video, found_new_video)
                                )

                if is_modified_playlist:
                    playlist_tuple = (ChangeType.MODIFY, old_playlist, found_new_playlist)
                    if playlist_tuple not in changelog_playlists:
                        changelog_playlists.append(playlist_tuple)

        if is_modified_game:
            game_tuple = (ChangeType.MODIFY, old_game, found_new_game)
            if game_tuple not in changelog_games:
                changelog_games.append(game_tuple)

    # sort by game date and stream date
    changelog_games.sort(key=lambda g: g[2].name)
    changelog_playlists.sort(key=lambda p: p[2].videos[0].date)
    changelog_videos.sort(key=lambda v: v[2].date)

    log(f"update_changelog", f"changelog timestamp {changelog_timestamp}")
    log(f"update_changelog", f"found {len(changelog_games)=}")
    log(f"update_changelog", f"found {len(changelog_playlists)=}")
    log(f"update_changelog", f"found {len(changelog_videos)=}")

    # write to file
    changelog_not_empty = bool(changelog_games or changelog_playlists or changelog_videos)
    if changelog_not_empty:

        def badges(element):
            if type(element) in [SovietsCloset.Game, SovietsCloset.Playlist]:
                if element.enabled and not element.recentlyUpdated:
                    return ""

                result = "("
                if not element.enabled:
                    result += "disabled"
                    if element.recentlyUpdated:
                        result += ", "
                if element.recentlyUpdated:
                    result += "recently updated"
                result += ")"
                return result

            elif type(element) == SovietsCloset.Video:
                if element.new:
                    return "(new)"
                else:
                    return ""

            raise RuntimeError()

        def link(element):
            return f"[{element.title}]({element.url})"

        def link_with_badges(element):
            return f"{link(element)} {badges(element)}".strip()

        def header(hn, change_type, element_type, element):
            return f"{'#' * hn} {change_type} {element_type} {link(element)}\n\n"

        def game_header(change_type, game):
            return header(3, change_type, "Game", game)

        def playlist_header(change_type, playlist):
            return header(4, change_type, "Playlist", playlist)

        # def video_header(change_type, video):
        #     return header(5, change_type, "Video", video)

        def category_changes(category_old, category_new):
            result = ""

            if category_old.enabled != category_new.enabled:
                if category_new.enabled:
                    result += f"- Is now enabled.\n"
                else:
                    result += f"- Is now disabled.\n"

            if category_old.recentlyUpdated != category_new.recentlyUpdated:
                if category_new.recentlyUpdated:
                    result += f"- Is now marked as recently updated.\n"
                else:
                    result += f"- Is no longer marked as recently updated.\n"

            if result:
                result += "\n"

            return result

        def video_changes(video_old, video_new):
            result = ""

            for key in ["title", "date", "number", "bunnyId"]:
                old_value = video_old.__getattribute__(key)
                new_value = video_new.__getattribute__(key)
                if old_value != new_value:
                    result += f"  - Changed {key} from `{old_value}` to `{new_value}`\n"

            if video_old.new != video_new.new:
                if video_new.new:
                    result += f"  - Is now marked as new.\n"
                else:
                    result += f"  - Is no longer marked as new.\n"

            return result

        changelog_md = "# Changelog\n\n"
        changelog_md += f"## {changelog_timestamp}Z\n\n"

        for game_change_type, game_one, game_two in changelog_games:
            changelog_md += game_header(game_change_type, game_two)
            changelog_md += category_changes(game_one, game_two)

            for playlist_change_type, playlist_one, playlist_two in changelog_playlists:
                if playlist_two.game == game_two:

                    changelog_md += playlist_header(playlist_change_type, playlist_two)
                    changelog_md += category_changes(playlist_one, playlist_two)

                    has_video_header = False
                    for video_change_type, video_one, video_two in changelog_videos:
                        if video_two.playlist == playlist_two:

                            if not has_video_header:
                                # videos need a heading to not mess up rendering of lists
                                changelog_md += f"##### Videos\n\n"
                                has_video_header = True

                            changelog_md += f"- {video_change_type} `v{video_two.id}` {link_with_badges(video_two)}\n"
                            changelog_md += video_changes(video_one, video_two)

                    changelog_md += "\n"

        changelog_path = Path("CHANGELOG.md")
        changelog_md = changelog_path.read_text().replace("# Changelog\n\n", changelog_md)
        changelog_path.write_text(changelog_md)
        log(f"update_changelog", "written CHANGELOG.md")

    log(f"update_changelog", "done")


if __name__ == "__main__":
    old_sovietscloset = SovietsCloset()

    update_raw_data()
    combine_data()

    update_oopsies()

    new_sovietscloset = SovietsCloset()
    update_changelog(old_sovietscloset, new_sovietscloset)
