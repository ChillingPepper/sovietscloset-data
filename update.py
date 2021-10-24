import json
import re
from pathlib import Path

import requests


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
        "pullZone": pull_zone,
        "videoLibraryId": video_library_id,
    }


def update_raw_data():
    print(f"[update_raw_data] start")

    global_vars = get_global_vars()
    json.dump(global_vars, open("raw/global.json", "w"), indent=2)

    base_url = global_vars["staticAssetsBase"]
    video_library_id = global_vars["videoLibraryId"]

    static_assets_timestamp = base_url.split("/")[-1]
    print(f"[update_raw_data] {static_assets_timestamp=}")

    if static_assets_timestamp == Path("raw/static_assets_timestamp").read_text():
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
    Path("raw/static_assets_timestamp").write_text(static_assets_timestamp)

    print(f"[update_raw_data] update done")


def combine_data():
    print(f"[combine_data...] start")
    sovietscloset = dict()

    global_vars = json.load(open("raw/global.json"))
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


if __name__ == "__main__":
    update_raw_data()
    combine_data()
