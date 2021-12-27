from enum import Enum
from pathlib import Path
from typing import TypeVar

from sovietscloset import SovietsCloset, SovietsClosetType
from utils import log


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

    changelog_games: list[
        tuple[
            ChangeType,
            SovietsCloset.Game,
            SovietsCloset.Game,
        ]
    ] = list()
    changelog_playlists: list[
        tuple[
            ChangeType,
            SovietsCloset.Playlist,
            SovietsCloset.Playlist,
        ]
    ] = list()
    changelog_videos: list[
        tuple[
            ChangeType,
            SovietsCloset.Video,
            SovietsCloset.Video,
        ]
    ] = list()

    def find_element(
        elements: list[SovietsClosetType],
        comparison_element: SovietsClosetType,
        key: str,
    ) -> SovietsClosetType | None:
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

        found_old_game = find_element(old_sovietscloset.games, new_game, "name")
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

                found_old_playlist = find_element(found_old_game.playlists, new_playlist, "name")
                if not found_old_playlist:
                    # added playlist with added videos in modified game
                    is_modified_game = True
                    changelog_playlists.append((ChangeType.ADD, new_playlist, new_playlist))
                    for new_video in new_playlist:
                        changelog_videos.append((ChangeType.ADD, new_video, new_video))
                else:

                    # find added videos
                    for new_video in new_playlist:
                        found_old_video = find_element(found_old_playlist.videos, new_video, "id")
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
        found_new_game = find_element(new_sovietscloset.games, old_game, "name")
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
                found_new_playlist = find_element(found_new_game.playlists, old_playlist, "name")
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
                        found_new_video = find_element(found_new_playlist.videos, old_video, "id")
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

        def badges(element: SovietsClosetType):
            if isinstance(element, SovietsCloset.Category):
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

            else:
                if element.new:
                    return "(new)"
                else:
                    return ""

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
