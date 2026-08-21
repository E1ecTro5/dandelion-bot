import asyncio
import re
from Models.file_model import AudioFile
import yt_dlp

def _download_file_sync(url: str) -> AudioFile:
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

        file = AudioFile(
            file_path = mp3_filename,
            title = info.get('title'),
            artist = info.get('artist') or info.get('uploader') or info.get('channel')
        )

        return file

def _check_title(file: AudioFile):
    if ' - ' not in file.title: return

    artist, _, title = file.title.partition(' - ') # first ' - ' will split the str

    file.artist = artist.strip()
    file.title = title.strip()

def _clean_title(file: AudioFile):
    title = file.title
    if not title: return ""

    trash_patterns = [
        r"NA\s*-\s*",
        r"\(Audio\)",
        r"\(Bonus\)",
        r"\(Bonus Track\)",
        r"\(Official Video\)",
        r"\(Official Audio\)",
        r"\[Official Video\]",
        r"\(Lyric Video\)",
        r"\(Lyrics\)",
        r"\(Live\)",
        r"\(Offical Visualizer\)",
        r"\(Visualizer\)",
        r"HD",
        r"4K",
    ]

    combined_pattern = "|".join(trash_patterns)
    cleaned = re.sub(combined_pattern, "", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    file.title = cleaned
    return None

async def download_audio(url: str) -> AudioFile:
    file = await asyncio.to_thread(_download_file_sync, url) # launching in a different thread
    _check_title(file)
    _clean_title(file)
    return file