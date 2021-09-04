import json
import re
from pathlib import Path

import requests


def js_to_json(code, vars={}):
    # vars is a dict of var, val pairs to substitute
    COMMENT_RE = r'/\*(?:(?!\*/).)*?\*/|//[^\n]*\n'
    SKIP_RE = r'\s*(?:{comment})?\s*'.format(comment=COMMENT_RE)
    INTEGER_TABLE = (
        (r'(?s)^(0[xX][0-9a-fA-F]+){skip}:?$'.format(skip=SKIP_RE), 16),
        (r'(?s)^(0+[0-7]+){skip}:?$'.format(skip=SKIP_RE), 8),
    )

    def fix_kv(m):
        v = m.group(0)
        if v in ('true', 'false', 'null'):
            return v
        elif v in ('undefined', 'void 0'):
            return 'null'
        elif v.startswith('/*') or v.startswith('//') or v.startswith('!') or v == ',':
            return ""

        if v[0] in ("'", '"'):
            v = re.sub(r'(?s)\\.|"', lambda m: {
                '"': '\\"',
                "\\'": "'",
                '\\\n': '',
                '\\x': '\\u00',
            }.get(m.group(0), m.group(0)), v[1:-1])
        else:
            for regex, base in INTEGER_TABLE:
                im = re.match(regex, v)
                if im:
                    i = int(im.group(1), base)
                    return '"%d":' % i if v.endswith(':') else '%d' % i

            if v in vars:
                return vars[v]

        return '"%s"' % v

    return re.sub(r'''(?sx)
        "(?:[^"\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^"\\]*"|
        '(?:[^'\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^'\\]*'|
        {comment}|,(?={skip}[\]}}])|
        void\s0|(?:(?<![0-9])[eE]|[a-df-zA-DF-Z_$])[.a-zA-Z_$0-9]*|
        \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:{skip}:)?|
        [0-9]+(?={skip}:)|
        !+
        '''.format(comment=COMMENT_RE, skip=SKIP_RE), fix_kv, code)

def download(url, progress=None):
    if not progress:
        print(f"[download.......] {url}")
    else:
        index = progress[0]
        max_ = progress[1]
        index_justified = str(index).rjust(len(str(max_)))
        print(f"[download.......] {index_justified}/{max_} {url}")
    # TODO handle errors
    return requests.get(url).text

def parse_nuxt_jsonp(nuxt_jsonp):
    NUXT_JSONP_RE = r'__NUXT_JSONP__\(.*?\(function\((?P<arg_keys>.*?)\)\{return\s(?P<js>\{.*?\})\}\((?P<arg_vals>.*?)\)'
    match = next(re.finditer(NUXT_JSONP_RE, nuxt_jsonp))
    arg_keys = match.group("arg_keys").split(',')
    arg_vals = match.group("arg_vals").split(',')
    js = match.group("js")
    
    args = {key: val for key, val in zip(arg_keys, arg_vals)}

    for key, val in args.items():
        if val in ('undefined', 'void 0'):
            args[key] = 'null'

    return json.loads(js_to_json(js, args))['data'][0]

def get_static_assets_base():
    html = download("https://sovietscloset.com")
    static_assets_base = re.findall(r'staticAssetsBase:\"(.*?)\"', html)[0]
    return f'https://sovietscloset.com{static_assets_base}'

def update_raw_data():
    print(f"[update_raw_data] start")

    base_url = get_static_assets_base()
    static_cache_id = base_url.split("/")[-1]
    print(f"[update_raw_data] {static_cache_id=}")

    if static_cache_id == Path("raw/static_cache_id").read_text():
        print(f"[update_raw_data] static_cache_id unchanged, aborting")
        return
    print(f"[update_raw_data] static_cache_id changed, updating")

    print(f"[update_raw_data] updating index data")
    sovietscloset = parse_nuxt_jsonp(download(f"{base_url}/payload.js"))["games"]
    json.dump(sovietscloset, open("raw/index.json", "w"), indent=2)

    print(f"[update_raw_data] updating video data")
    video_ids = [stream["id"] for game in sovietscloset for subcategory in game["subcategories"] for stream in subcategory["streams"]]
    for i, video_id in enumerate(video_ids, start=1):
        stream_details_url = f"{base_url}/video/{video_id}/payload.js"
        stream_details_jsonp = download(stream_details_url, (i, len(video_ids)))
        stream_details = parse_nuxt_jsonp(stream_details_jsonp)["stream"]
        json.dump(stream_details, open(f"raw/video/{video_id}.json", "w"), indent=2)

    print(f"[update_raw_data] caching static_cache_id")
    Path("raw/static_cache_id").write_text(static_cache_id)

    print(f"[update_raw_data] update done")

def combine_data():
    print(f"[combine_data...] start")

    raw_index = json.load(open("raw/index.json"))

    sovietscloset = list()
    for index_game in raw_index:
        game = dict()
        for key in ["name", "slug", "enabled", "recentlyUpdated"]:
            game[key] = index_game[key]

        game["categories"] = list()
        for index_category in index_game["subcategories"]:
            category = dict()
            for key in ["name", "slug", "enabled", "recentlyUpdated"]:
                category[key] = index_category[key]
            
            category['videos'] = list()
            for index_video in index_category["streams"]:
                raw_video = json.load(open(f"raw/video/{index_video['id']}.json"))
                combined_video = {**index_video, **raw_video}

                video = dict()
                for key in ["id", "date", "number", "useBunny", "bunnyId", "new"]:
                    video[key] = combined_video[key]
                
                category['videos'].append(video)
            game["categories"].append(category)
        sovietscloset.append(game)
    
    json.dump(sovietscloset, open("sovietscloset.json", "w"), indent=2)
    print(f"[combine_data...] written to sovietscloset.json")

if __name__ == "__main__":
    update_raw_data()
    combine_data()
