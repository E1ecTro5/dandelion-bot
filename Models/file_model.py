from dataclasses import dataclass

@dataclass
class AudioFile:
    file_path: str
    title: str
    artist: str
    album: str | None = None
    album_artist: str | None = None
    year: str | None = None