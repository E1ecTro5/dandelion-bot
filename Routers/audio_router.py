import os

from Utils import audio_configurator
from aiogram import Router
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from Models.main_models import Album, Track
from Utils.bot_functions import try_get_audio, identify_downloaded_audio, track_from_audio, try_get_tags, \
    try_get_album_cover, prepare_download_id, generate_answer_card
from Utils.download_manager import dm_instance

# create router to pass in the main.py
router = Router()

class ConfirmAction(CallbackData, prefix="confirm_dl"):
    action: str # action type
    download_id: str

@router.message(Command("dlp"))
async def dlp_handler(message: Message):
    audio_file, _ = await try_get_audio(message) # get the audio file
    if audio_file is None: return await message.answer("NONE AUDIO FILE")
    await identify_downloaded_audio(message, audio_file) # parses AudioFile to Track
    track_file = await track_from_audio(audio_file) # Track() from AudioFile()

    # get the tags and cover
    try:
        track, album = await try_get_tags(message, audio_file, track_file) # name speaks for itself
        if track is None: return await message.answer("NONE TRACK FILE") # just in case

        album_cover = await try_get_album_cover(message, album) # name speaks for itself
        if album_cover is None: return await message.answer("NONE ALBUM COVER FILE") # just in case

        # creates download_id in the memory ; need for multiple downloads
        download_id = await prepare_download_id(audio_file, track, album, album_cover)

        # card with audio details (with tags and cover) ; keyboard with answers
        await generate_answer_card(message, track, album, album_cover, download_id)

    except Exception as e:
        await message.answer(f"Error during download: {e}")

@router.callback_query(ConfirmAction.filter())
async def process_confirm_callback(query: CallbackQuery, callback_data: ConfirmAction):
    await query.answer()

    download_id = callback_data.download_id
    data = dm_instance.get_and_pop(download_id)

    if not data:
        await query.message.answer("Download session is outdated or file has not been found.")
        return

    file_path = data["file_path"]
    track: Track = data["track"]
    album: Album = data["album"]
    cover_url = data["cover_url"]

    try:
        if callback_data.action == "cancel":
            await query.message.delete()
            await query.message.answer("Download cancelled.")
            return

        # update msg
        status_suffix = "\n\nApplying tags..." if callback_data.action == "apply" else "\n\nSkipped."
        if query.message.photo: await query.message.edit_caption(caption=f"{query.message.caption}{status_suffix}")
        else: await query.message.edit_text(text=f"{query.message.text}{status_suffix}")

        if callback_data.action == "apply":
            try: await audio_configurator.apply_tags(file_path, track, album, cover_url)
            except Exception as e: await query.message.answer(f"Error while applying tags: {e}")

        if os.path.exists(file_path):
            audio_file = FSInputFile(file_path)
            await query.message.answer_audio(audio_file)
            os.remove(file_path)
        else:
            await query.message.answer("File has not been found on server.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)