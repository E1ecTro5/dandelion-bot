import os
from Utils import audio_configurator
import uuid
from aiogram import Router
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from Models.main_models import Album, Track
from Utils.bot_functions import try_get_audio, identify_downloaded_audio, track_from_audio
from Utils.configuration_functions import _set_album_cover, _generate_caption_text

# create router to pass in the main.py
router = Router()

# temp storage ; how about you just use Redis in future instead of this?
PENDING_DOWNLOADS = {}

class ConfirmAction(CallbackData, prefix="confirm_dl"):
    action: str # action type
    download_id: str

@router.message(Command("dlp"))
async def dlp_handler(message: Message):
    audio_file = await try_get_audio(message) # get the audio file
    await identify_downloaded_audio(message, audio_file) # parses AudioFile to Track
    trackFile = await track_from_audio(audio_file) # Track() from AudioFile()

    # get the tags and cover
    try:
        # tags
        # make it try_get_tags
        try: track, album = await audio_configurator.setup_tags(audio_file)
        except Exception as e:
            await message.answer(f"Tag setup failed: {e}")
            track = trackFile
            album = Album()

        # cover
        try: album_cover = await _set_album_cover(album)
        except Exception as e:
            await message.answer(f"Error while getting album cover: {e}")
            album_cover = None

        caption_text = await _generate_caption_text(album, track)

        download_id = str(uuid.uuid4())[:8]
        PENDING_DOWNLOADS[download_id] = {
            "file_path": audio_file.file_path,
            "track": track,
            "album": album,
            "cover_url": album_cover
        }

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Apply tags",
                    callback_data=ConfirmAction(action="apply", download_id=download_id).pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="Skip",
                    callback_data=ConfirmAction(action="skip", download_id=download_id).pack()
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data=ConfirmAction(action="cancel", download_id=download_id).pack()
                )
            ]
        ])

        if album_cover:
            try:
                await message.answer_photo(
                    photo=album_cover,
                    caption=caption_text,
                    reply_markup=keyboard,
                )
                return
            except Exception:
                pass  # if cover damaged / not found

        await message.answer(caption_text, reply_markup=keyboard)

    except Exception as e:
        await message.answer(f"Error during download: {e}")
    finally:
        pass
        # if status_msg: await status_msg.delete()

@router.callback_query(ConfirmAction.filter())
async def process_confirm_callback(query: CallbackQuery, callback_data: ConfirmAction):
    await query.answer()

    download_id = callback_data.download_id
    data = PENDING_DOWNLOADS.pop(download_id, None)

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