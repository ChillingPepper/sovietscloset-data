import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar


class SovietsCloset:
    @dataclass
    class BunnyCdn:
        pullZone: str
        videoLibraryId: str

    @dataclass
    class Video:
        game: "SovietsCloset.Game"
        playlist: "SovietsCloset.Playlist"

        title: str
        url: str

        id: int
        date: str
        number: int
        bunnyId: str | None
        new: bool

        def __eq__(self, other: "SovietsCloset.Video") -> bool:
            return (
                self.id == other.id
                and self.date == other.date
                and self.number == other.number
                and self.bunnyId == other.bunnyId
                and self.new == other.new
            )

    @dataclass
    class Category:
        title: str
        url: str

        name: str
        slug: str
        enabled: bool
        recentlyUpdated: bool

    @dataclass
    class Playlist(Category):
        game: "SovietsCloset.Game"

        videos: list["SovietsCloset.Video"]

        def __eq__(self, other: "SovietsCloset.Playlist") -> bool:
            return SovietsCloset.Category.__eq__(self, other)

        def __iter__(self):
            yield from self.videos

        def __getitem__(self, i: int):
            return self.videos[i]

    @dataclass
    class Game(Category):
        playlists: list["SovietsCloset.Playlist"]

        def __eq__(self, other: "SovietsCloset.Game") -> bool:
            return SovietsCloset.Category.__eq__(self, other)

        def __iter__(self):
            yield from self.playlists

        def __getitem__(self, i: int):
            return self.playlists[i]

        @property
        def videos(self):
            for playlist in self.playlists:
                yield from playlist

    timestamp: datetime
    bunnyCdn: BunnyCdn
    games: list[Game]

    _filename: str
    _json: dict[str, Any]

    def __init__(self, filename: str = "sovietscloset.json"):
        self._filename = filename
        self._json = json.load(open(filename))

        self.timestamp = datetime.utcfromtimestamp(self._json["timestamp"])
        self.bunny_cdn = SovietsCloset.BunnyCdn(**self._json["bunnyCdn"])

        self.games = list()
        for game in self._json["games"]:
            playlists = list[SovietsCloset.Playlist]()
            for playlist in game["playlists"]:
                playlist["game"] = None
                for i, video in enumerate(playlist["videos"]):
                    video["game"] = None
                    video["playlist"] = None
                    playlist["videos"][i] = SovietsCloset.Video(**video)
                playlists.append(SovietsCloset.Playlist(**playlist))
            game["playlists"] = playlists
            self.games.append(SovietsCloset.Game(**game))

        for game in self.games:
            for playlist in game:
                playlist.game = game
                for video in playlist:
                    video.game = game
                    video.playlist = playlist

    def __iter__(self):
        yield from self.games

    def __getitem__(self, i: int):
        return self.games[i]

    @property
    def playlists(self):
        for game in self.games:
            yield from game.playlists

    @property
    def videos(self):
        for playlist in self.playlists:
            yield from playlist


SovietsClosetType = TypeVar(
    "SovietsClosetType",
    SovietsCloset.Game,
    SovietsCloset.Playlist,
    SovietsCloset.Video,
)
