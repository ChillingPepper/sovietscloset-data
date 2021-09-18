export interface SovietsCloset {
    bunnyCdn: {
        pullZone: string;
        videoLibraryId: string;
    }
    games: SovietsClosetGame[];
}

export interface SovietsClosetCategory {
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
    id: number;
    date: string;
    number: number;
    bunnyId: string | null;
    new: boolean;
}

import SovietsClosetJson from "./sovietscloset.json"
export const SovietsCloset = SovietsClosetJson as SovietsCloset
