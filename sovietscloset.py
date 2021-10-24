from datetime import datetime
import json
from dataclasses import dataclass
from typing import List, Optional


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
        id: int
        date: str
        number: int
        bunnyId: Optional[str]
        new: bool

    @dataclass
    class Category:
        name: str
        slug: str
        enabled: bool
        recentlyUpdated: bool

    @dataclass
    class Playlist(Category):
        game: "SovietsCloset.Game"

        videos: List["SovietsCloset.Video"]

        def __iter__(self):
            for video in self.videos:
                yield video

        def __getitem__(self, i):
            return self.videos[i]

    @dataclass
    class Game(Category):
        playlists: List["SovietsCloset.Playlist"]

        def __iter__(self):
            for playlist in self.playlists:
                yield playlist

        def __getitem__(self, i):
            return self.playlists[i]

    timestamp: datetime
    bunnyCdn: BunnyCdn
    games: List[Game]

    _filename: str
    _json: dict

    def __init__(self, filename="sovietscloset.json"):
        self._filename = filename
        self._json = json.load(open(filename))

        self.timestamp = datetime.utcfromtimestamp(self._json["timestamp"])
        self.bunny_cdn = SovietsCloset.BunnyCdn(**self._json["bunnyCdn"])

        self.games = list()
        for game in self._json["games"]:
            playlists = list()
            for playlist in game["playlists"]:
                playlist["game"] = None
                for i, video in enumerate(playlist["videos"]):
                    video["game"] = None
                    video["playlist"] = None
                    playlist["videos"][i] = SovietsCloset.Video(**video)
                playlists.append(SovietsCloset.Playlist(**playlist))
            game["playlists"] = playlists
            self.games.append(SovietsCloset.Game(**game))

        for game in self:
            for playlist in game:
                playlist.game = game
                for video in playlist:
                    video.game = game
                    video.playlist = playlist

    def __iter__(self):
        for game in self.games:
            yield game

    def __getitem__(self, i):
        return self.games[i]
