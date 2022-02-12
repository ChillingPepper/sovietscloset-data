import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import eventlet
import requests
from eventlet.greenthread import sleep

if not TYPE_CHECKING:
    from eventlet.green.urllib.request import urlopen
else:
    from urllib.request import urlopen

from utils import log


def js_to_json(code: str, vars: dict[str, str] = {}):
    # vars is a dict of var, val pairs to substitute
    COMMENT_RE = r"/\*(?:(?!\*/).)*?\*/|//[^\n]*\n"
    SKIP_RE = r"\s*(?:{comment})?\s*".format(comment=COMMENT_RE)
    INTEGER_TABLE = (
        (r"(?s)^(0[xX][0-9a-fA-F]+){skip}:?$".format(skip=SKIP_RE), 16),
        (r"(?s)^(0+[0-7]+){skip}:?$".format(skip=SKIP_RE), 8),
    )

    def fix_kv(match: re.Match[str]):
        value = match.group(0)
        if value in ("true", "false", "null"):
            return value
        elif value in ("undefined", "void 0"):
            return "null"
        elif (
            value.startswith("/*")
            or value.startswith("//")
            or value.startswith("!")
            or value == ","
        ):
            return ""

        if value[0] in ("'", '"'):
            value = re.sub(
                r'(?s)\\.|"',
                lambda m: {
                    '"': '\\"',
                    "\\'": "'",
                    "\\\n": "",
                    "\\x": "\\u00",
                }.get(m.group(0), m.group(0)),
                value[1:-1],
            )
        else:
            for regex, base in INTEGER_TABLE:
                integer_match = re.match(regex, value)
                if integer_match:
                    i = int(integer_match.group(1), base)
                    return f'"{i}":' if value.endswith(":") else str(i)

            if value in vars:
                return vars[value]

        return f'"{value}"'

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


def download(url: str, headers: dict[str, str] = {}, progress: tuple[int, int] | None = None):
    if not progress:
        log("download", url)
    else:
        index = progress[0]
        max_ = progress[1]
        index_justified = str(index).rjust(len(str(max_)), "0")
        log("download", f"{index_justified}/{max_} {url}")
    # TODO handle errors
    return requests.get(url, headers=headers).text


def parse_nuxt_jsonp(nuxt_jsonp: str):
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
        re.finditer(r"https:\/\/(?P<pull_zone>.*)\.b-cdn\.net\/%s\/" % video_id, embed_html), None
    )
    if not embed_match:
        log("get_global_vars", f"failed to find BunnyCDN pull zone in:\n\n{embed_html}")
        raise RuntimeError("failed to find BunnyCDN pull zone")
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

    def update_raw_video(video_id: int):
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
    sovietscloset = dict[str, Any]()

    global_vars = json.load(open("raw/global.json"))
    sovietscloset["timestamp"] = global_vars["staticAssetsTimestamp"]
    sovietscloset["bunnyCdn"] = dict()
    for key in ["pullZone", "videoLibraryId"]:
        sovietscloset["bunnyCdn"][key] = global_vars[key]

    raw_index = json.load(open("raw/index.json"))
    sovietscloset["games"] = list()
    for index_game in raw_index:
        game = dict[str, Any]()
        game["title"] = index_game["name"]
        game["url"] = f"https://sovietscloset.com/{index_game['slug']}"
        for key in ["name", "slug", "enabled", "recentlyUpdated"]:
            game[key] = index_game[key]

        game["playlists"] = list()
        for index_subcategory in index_game["subcategories"]:
            playlist = dict[str, Any]()
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

                video = dict[str, Any]()
                video["title"] = f"{playlist['title']} #{combined_video['number']}"
                video["url"] = f"https://sovietscloset.com/video/{combined_video['id']}"
                for key in ["id", "date", "number", "bunnyId", "new"]:
                    video[key] = combined_video[key]

                playlist["videos"].append(video)
            game["playlists"].append(playlist)
        sovietscloset["games"].append(game)

    json.dump(sovietscloset, open("sovietscloset.json", "w"), indent=2)
    log("combine_data", "written to sovietscloset.json")


def update_data():
    update_raw_data()
    combine_data()
