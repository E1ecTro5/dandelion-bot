import asyncio
import yt_dlp

def _download_sync(url: str) -> str:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',

        # using our own cookies
        'cookiefile': '/app/cookies.txt', # located near the main/docker files

        # dlp needs it to work properly
        'remote_components': ['ejs:github'],

        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'quiet': False,  # leaving here for debug
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True) # metafiles
        filename = ydl.prepare_filename(info) # getting filename after post-processing
        filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename

async def download_audio(url: str) -> str:
    return await asyncio.to_thread(_download_sync, url) # launching in a different thread