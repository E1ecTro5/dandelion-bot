import asyncio
import re
from typing import Any

import yt_dlp

def _download_sync(url: str) -> dict[str, str | None | Any]:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(uploader)s - %(title)s.%(ext)s',

        # using our own cookies
        'cookiefile': '/app/cookies.txt', # located near the main/docker files

        # dlp needs it to work properly
        'js_engine': 'deno',
        'remote_components': ['ejs:github'],

        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '256',
        }],
        'quiet': False,  # leaving here for debug
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True) # metafiles
        mp3_filename = ydl.prepare_filename(info) # getting filename after post-processing
        mp3_filename = mp3_filename.rsplit('.', 1)[0] + '.mp3'

        title = info.get('title') or mp3_filename
        artist = info.get('artist') or info.get('uploader') or info.get('channel') or "Unknown"
        # album = info.get('album') or "" # maybe in future if needed?

        if title.__contains__(' - '):
            artist, title = get_strings_from_title(artist, title)

        title = clean_string(title)

        return {
            "file_path": mp3_filename,
            "title": title,
            "artist": artist,
            # "album": album
        }

def get_strings_from_title(artist:str, title: str) -> tuple[str, str]:
    artist = title[:title.index(' - ')]
    title = title[(title.index(' - ')) + 3:]
    return artist, title

def clean_string(string: str) -> str:
    if not string: return ""

    trash_patterns = [
        r"NA\s*-\s*",
        r"\(Audio\)",
        r"\(Official Video\)",
        r"\(Official Audio\)",
        r"\[Official Video\]",
        r"\(Lyric Video\)",
        r"\(Lyrics\)",
        r"\(Offical Visualizer\)"
        r"\(Visualizer\)",
        r"HD",
        r"4K",
    ]

    combined_pattern = "|".join(trash_patterns)
    cleaned = re.sub(combined_pattern, "", string, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned

async def download_audio(url: str) -> str:
    return await asyncio.to_thread(_download_sync, url) # launching in a different thread