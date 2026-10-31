from Models.file_model import AudioFile
from Models.main_models import Track, Album
from Utils import media_installer, audio_configurator

async def _check_url(url: str | None) -> str:
    """Check if url is valid"""
    if url is None: raise Exception("Null url.")

    args = url.split(maxsplit=1)
    if len(args) < 2: raise Exception("Please enter a valid URL. Use /dlp <URL>")

    return args[1]

async def _get_audio(url) -> AudioFile:
    """Downloads the audio and returns it"""
    audio_file = await media_installer.download_audio(url)
    if not audio_file: raise Exception("Couldn't download the file.")

    file_path = audio_file.file_path
    if not file_path: raise Exception("Couldn't find the file on server.")

    return audio_file

async def _set_album_cover(album: Album) -> str | None:
    """Downloads the album cover and returns it"""
    if album.title and album.artist:
        album_cover = await audio_configurator.get_album_cover(album.title, album.artist)
        return album_cover

    return None