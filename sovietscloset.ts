export interface SovietsCloset {
    timestamp: number;
    bunnyCdn: {
        pullZone: string;
        videoLibraryId: string;
    }
    games: SovietsClosetGame[];
}

export interface SovietsClosetCategory {
    title: string;
    url: string;
    name: string;
    slug: string;
    enabled: boolean;
    recentlyUpdated: boolean;
}

export interface SovietsClosetGame extends SovietsClosetCategory {
    playlists: SovietsClosetPlaylist[];
}

export interface SovietsClosetPlaylist extends SovietsClosetCategory {
    videos: SovietsClosetVideo[];
}

export interface SovietsClosetVideo {
    title: string;
    url: string;
    id: number;
    date: string;
    number: number;
    bunnyId: string | null;
    new: boolean;
}

import SovietsClosetJson from "./sovietscloset.json"
export const SovietsCloset = SovietsClosetJson as SovietsCloset
