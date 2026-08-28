from dataclasses import dataclass

@dataclass
class AudioFile:
    file_path: str
    title: str
    artist: str