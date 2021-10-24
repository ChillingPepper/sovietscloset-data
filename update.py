import json
import re
from pathlib import Path
from typing import Dict, List

import requests

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


def download(url, headers={}, progress=None):
    if not progress:
        print(f"[download.......] {url}")
    else:
        index = progress[0]
        max_ = progress[1]
        index_justified = str(index).rjust(len(str(max_)), "0")
        print(f"[download.......] {index_justified}/{max_} {url}")
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
    print(f"[update_raw_data] start")

    global_vars = get_global_vars()
    json.dump(global_vars, open("raw/global.json", "w"), indent=2)

    base_url = global_vars["staticAssetsBase"]
    static_assets_timestamp = global_vars["staticAssetsTimestamp"]

    print(f"[update_raw_data] {static_assets_timestamp=}")

    if static_assets_timestamp == int(Path("raw/static_assets_timestamp").read_text()):
        print(f"[update_raw_data] static_assets_timestamp unchanged, aborting")
        return
    print(f"[update_raw_data] static_assets_timestamp changed, updating")

    print(f"[update_raw_data] updating index data")
    sovietscloset = parse_nuxt_jsonp(download(f"{base_url}/payload.js"))["games"]
    json.dump(sovietscloset, open("raw/index.json", "w"), indent=2)

    print(f"[update_raw_data] updating video data")
    video_ids = [
        stream["id"]
        for game in sovietscloset
        for subcategory in game["subcategories"]
        for stream in subcategory["streams"]
    ]
    for i, video_id in enumerate(video_ids, start=1):
        stream_details_url = f"{base_url}/video/{video_id}/payload.js"
        stream_details_jsonp = download(stream_details_url, progress=(i, len(video_ids)))
        # Path("debug.video.payload.js").write_text(stream_details_jsonp)
        stream_details = parse_nuxt_jsonp(stream_details_jsonp)["stream"]
        json.dump(stream_details, open(f"raw/video/{video_id}.json", "w"), indent=2)

    print(f"[update_raw_data] caching static_assets_timestamp")
    Path("raw/static_assets_timestamp").write_text(str(static_assets_timestamp))

    print(f"[update_raw_data] update done")


def combine_data():
    print(f"[combine_data...] start")
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
        for key in ["name", "slug", "enabled", "recentlyUpdated"]:
            game[key] = index_game[key]

        game["playlists"] = list()
        for index_subcategory in index_game["subcategories"]:
            playlist = dict()
            for key in ["name", "slug", "enabled", "recentlyUpdated"]:
                playlist[key] = index_subcategory[key]

            playlist["videos"] = list()
            for index_video in index_subcategory["streams"]:
                raw_video = json.load(open(f"raw/video/{index_video['id']}.json"))
                combined_video = {**index_video, **raw_video}

                video = dict()

                video["title"] = game["name"]
                if playlist["name"] != "Misc":
                    video["title"] += f" - {playlist['name']}"
                video["title"] += f" #{combined_video['number']}"

                for key in ["id", "date", "number", "bunnyId", "new"]:
                    video[key] = combined_video[key]

                playlist["videos"].append(video)
            game["playlists"].append(playlist)
        sovietscloset["games"].append(game)

    json.dump(sovietscloset, open("sovietscloset.json", "w"), indent=2)
    print(f"[combine_data...] written to sovietscloset.json")


def update_oopsies():
    print("[update_oopsies.] start")
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
                        print(video.title)
                        sorting_date.append(video)

                    # sorting by number
                    if video.number < last_video.number:
                        print(video.title)
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
            title = playlist.game.name
            url = f"https://sovietscloset.com/{playlist.game.slug}"
            if playlist.name != "Misc":
                title += f" - {playlist.name}"
                url += f"/{playlist.slug}"

            if title != last_title:
                oopsies_md += f"- [{title}]({url})\n"
                last_title = title

            for i in range(start, stop + 1):
                oopsies_md += f"  - {title} #{i}\n"
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
    print("[update_oopsies.] written to OOPSIES.md")


if __name__ == "__main__":
    update_raw_data()
    combine_data()
    update_oopsies()
