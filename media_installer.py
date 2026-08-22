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
    if not title:
        file.title = ""
        return None

    # crop everything starting with: (..., [..., feat, ft, official, 4k, hd, video, visualizer
    cut_pattern = r"\s*(?:[\(\[]|\b(?:feat|ft|official|audio|video|visualizer|lyric|lyrics|4k|hd|prod)\b).*"

    # check if we actually need to crop
    cleaned = re.sub(cut_pattern, "", title, flags=re.IGNORECASE)

    # crop smth like 'NA - ' just in case
    cleaned = re.sub(r"^\s*NA\s*[-–—]\s*", "", cleaned, flags=re.IGNORECASE)

    # remove unnecessary punctuations and whitespaces
    cleaned = cleaned.strip(" -–—,.")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    file.title = cleaned
    return None

def _clean_artists(file: AudioFile):
    artist = file.artist
    if not artist:
        file.artist = ""
        return None

    delimiters = [
        r"featuring", r"feat\.", r"feat", r"ft\.", r"ft",
        r"with", r"and", r"&", r",", r"/", r"\\"
    ]

    escaped_patterns = []
    for d in delimiters:
        escaped = re.escape(d.strip())
        if re.search(r'\w', d):
            escaped_patterns.append(rf"\b{escaped}\b")
        else:
            escaped_patterns.append(escaped)

    combined_pattern = "|".join(escaped_patterns)
    parts = re.split(combined_pattern, artist, maxsplit=1, flags=re.IGNORECASE)

    first_artist = parts[0].strip(" -–—,.")
    first_artist = re.sub(r"\s+", " ", first_artist).strip()

    file.artist = first_artist
    return None

async def download_audio(url: str) -> AudioFile:
    file = await asyncio.to_thread(_download_file_sync, url) # launching in a different thread
    _check_title(file)
    _clean_title(file)
    _clean_artists(file)
    return file