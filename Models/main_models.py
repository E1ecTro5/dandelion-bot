from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Track:
    title: str
    artists: str
    album_title: str
    disc: int
    position: int
    file_path: str

@dataclass
class Album:
    title: str
    artist: str
    year: str
    main_genre: str
    subgenres: List[str] = field(default_factory=list)
    cover_url: [Optional[str]] = None
    total_tracks: int = 0