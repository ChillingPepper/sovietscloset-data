import json
from pathlib import Path

from sovietscloset import SovietsCloset
from utils import log


def bunnycdn_wrong_tag_load_raw():
    wrong_tag = list[int]()

    for f in Path("raw/video").iterdir():
        raw = json.load(f.open())
        use_bunny: bool = raw["useBunny"]
        bunny_id: str = raw["bunnyId"]
        stream_id: int = raw["streamId"]

        if not use_bunny:
            if bunny_id:
                wrong_tag.append(stream_id)

    return wrong_tag


def update_oopsies():
    log("update_oopsies", "start")
    bunnycdn_wrong_tag_raw = bunnycdn_wrong_tag_load_raw()
    bunnycdn_wrong_tag: list[SovietsCloset.Video] = list()

    missing_bunnycdn: list[SovietsCloset.Video] = list()
    missing_completely: list[tuple[SovietsCloset.Playlist, int, int]] = list()

    sorting_date: list[SovietsCloset.Video] = list()
    sorting_number: list[SovietsCloset.Video] = list()

    dupes_date: dict[str, list[SovietsCloset.Video]] = dict()
    dupes_number: dict[int, list[SovietsCloset.Video]] = dict()
    dupes_bunnycdn: dict[str, list[SovietsCloset.Video]] = dict()

    sovietscloset = SovietsCloset()
    for game in sovietscloset:
        for playlist in game:
            # missing bunnycdn
            for video in playlist:
                if not video.bunnyId:
                    missing_bunnycdn.append(video)

            # wrong usesBunny tag
            for video in playlist:
                if video.id in bunnycdn_wrong_tag_raw:
                    bunnycdn_wrong_tag.append(video)

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
            dates: dict[str, list[SovietsCloset.Video]] = dict()
            numbers: dict[int, list[SovietsCloset.Video]] = dict()
            bunnycdn: dict[str, list[SovietsCloset.Video]] = dict()

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
                        for video in temp_dict[key]:
                            if video not in dupes_dict[key]:
                                dupes_dict[key].append(video)

    oopsies_md = "# Oopsies\n\n"
    oopsies_md += f"Last updated at {sovietscloset.timestamp.isoformat(timespec='seconds')}Z.\n\n"

    # wrongly tagged
    oopsies_md += "## Wrong Tags\n\n"

    oopsies_md += "### BunnyCDN tag\n\n"
    oopsies_md += "This list includes all videos that are available on BunnyCDN but are tagged as though they aren't.\n\n"

    if len(bunnycdn_wrong_tag):
        for video in bunnycdn_wrong_tag:
            oopsies_md += f"- [{video.title}](https://sovietscloset.com/video/{video.id})\n"
    else:
        oopsies_md += "All videos are tagged correctly. :tada:\n"
    oopsies_md += "\n"

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
            for key, videos in sorted(dupes.items()):
                oopsies_md += f"- {capitalized_name}: {key}\n"
                for video in sorted(videos, key=lambda v: f"{v.title}{v.id}"):
                    oopsies_md += f"  - [{video.title}](https://sovietscloset.com/video/{video.id}) (id: {video.id})\n"
        else:
            oopsies_md += f"All videos have a unique {name}. :tada:\n"

    Path("OOPSIES.md").write_text(oopsies_md)
    log("update_oopsies", "written to OOPSIES.md")
