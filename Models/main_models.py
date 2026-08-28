from dataclasses import dataclass

# make them all nullable so you can init their properties later in the code
@dataclass
class Track:
    title: str | None = None
    artists: str | None = None
    file_path: str | None = None
    album_title: str | None = None
    disc: int | None = None
    position: int | None = None

@dataclass
class Album:
    title: str | None = None
    artist: str | None = None
    year: str | None = None
    main_genre: str | None = None
    cover_url: str | None = None
    total_tracks: int | None = None