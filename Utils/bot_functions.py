from aiogram.types import Message

from Models.file_model import AudioFile
from Models.main_models import Track
from Utils.configuration_functions import _check_url, _get_audio

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