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

async def _generate_caption_text(album: Album, track: Track) -> str:
    """Prepare text for caption with detailed album and track info"""
    caption_text = (
        f"Album: {album.title or 'N/A'}\n"
        f"Album Artist: {album.artist or 'N/A'}\n"
        f"Year: {album.year or 'N/A'}\n"
        f"Genre: {album.main_genre or 'N/A'}\n"
        f"Total tracks: {album.total_tracks or 'N/A'}\n\n"

        f"Track: {track.title or 'N/A'}\n"
        f"Artists: {track.artists or 'N/A'}\n"
        f"Disc number: {track.disc or 1}\n"
        f"Track position: {track.position or 1}/{album.total_tracks or 1}\n"
    )

    return caption_text