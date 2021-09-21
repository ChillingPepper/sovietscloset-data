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
        videos: List["SovietsCloset.Video"]

    @dataclass
    class Game(Category):
        playlists: List["SovietsCloset.Playlist"]

    bunnyCdn: BunnyCdn
    games: List[Game]

    _filename: str
    _json: dict

    def __init__(self, filename="sovietscloset.json"):
        self._filename = filename
        self._json = json.load(open(filename))

        self.bunny_cdn = SovietsCloset.BunnyCdn(**self._json["bunnyCdn"])

        self.games = list()
        for game in self._json["games"]:
            playlists = list()
            for playlist in game["playlists"]:
                videos = list()
                for video in playlist["videos"]:

                    videos.append(SovietsCloset.Video(**video))
                playlist["videos"] = videos
                playlists.append(SovietsCloset.Playlist(**playlist))
            game["playlists"] = playlists
            self.games.append(SovietsCloset.Game(**game))
