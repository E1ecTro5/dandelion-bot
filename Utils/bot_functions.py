import uuid

from aiogram.types import Message

from Models.file_model import AudioFile
from Models.main_models import Track, Album
from Utils import audio_configurator
from Utils.configuration_functions import _check_url, _get_audio, _set_album_cover
from Utils.download_manager import dm_instance


async def try_get_audio(message: Message) -> tuple[AudioFile | None, Message | None]:
    """Accepts Message, parses it, checks the url, downloads the file and returns as AudioFile if available"""
    try:
        url = await _check_url(message.text)
        status_msg = await message.answer("Downloading...")
        audio_file = await _get_audio(url)
        return audio_file, status_msg
    except:
        status_msg = await message.answer(f"Couldn't download the audio.")
        return None, status_msg

async def identify_downloaded_audio(message: Message, audio_file: AudioFile):
    """Accepts AudioFile, answers a message, which tells about file tags (title, artists, album if found, year if found)"""
    await message.answer(f"Downloaded file:\n"
                         f"Title: {audio_file.title}\n"
                         f"Artists: {audio_file.artist}\n\n"
                         f"Identifiers in file:\n"
                         f"Album: {audio_file.album}\n"
                         f"Album artist: {audio_file.album_artist}\n"
                         f"Year: {audio_file.year}\n\n"
                         f"Searching for tags...")

async def track_from_audio(file: AudioFile) -> Track:
    """Accepts AudioFile and returns Track with title, artists and path. Still not full Track info..."""
    track = Track(
        title=file.title, # never will be null
        artists=file.artist.split(", ")[0], # never will be null
        file_path=file.file_path # same goes here
    )

    return track

async def try_get_tags(message: Message, audio_file: AudioFile, track_file: Track):
    try:
        await message.answer(f"Searching for tags in Discogs base...")
        track, album = await audio_configurator.setup_tags(audio_file)
        return track, album
    except Exception as e:
        await message.answer(f"Tag setup failed: {e}")
        return None, None

async def try_get_album_cover(message: Message, album: Album):
    try:
        await message.answer(f"Downloading album cover...")
        album_cover = await _set_album_cover(album)
        return album_cover
    except Exception as e:
        await message.answer(f"Error while getting album cover: {e}")
        return None

async def prepare_download_id(audio_file: AudioFile, track: Track, album: Album, album_cover: str) -> str:
    download_id = str(uuid.uuid4())[:8] # generate id
    data = {
        "file_path": audio_file.file_path,
        "track": track,
        "album": album,
        "cover_url": album_cover
    }

    dm_instance.add(download_id, data) # add to DownloadManager instance

    return download_id # make sure to return the id back