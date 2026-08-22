import os
import audio_configurator
import media_installer
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from Models.file_model import AudioFile
from Models.main_models import Album, Track

# create router to pass in the main.py
router = Router()

# temp storage
PENDING_DOWNLOADS = {}

class ConfirmAction(CallbackData, prefix="confirm_dl"):
    action: str # action type
    download_id: str

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Welcome!")

@router.message(Command("dlp"))
async def dlp_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Please pass a link: `/dlp <link>`")
        return

    url = args[1]
    status_msg = await message.answer("Downloading...")

    try:
        audio_file = await _get_audio(url)

        track_name: str | None = audio_file.title
        artist_name: str | None = str(audio_file.artist).split(", ")[0] if audio_file.artist else None
        file_path: str | None = audio_file.file_path

        await message.answer(f"Downloaded: {track_name} by {artist_name}") # log

        # tags
        try:
            track, album = await audio_configurator.setup_tags(audio_file)
        except Exception as e:
            await message.answer(f"Tag setup failed: {e}")
            track = Track(title=track_name, artists=artist_name, file_path=file_path)
            album = Album()

        # cover
        album_cover: str | None = None
        if album.title and album.artist:
            try:
                album_cover = await audio_configurator.get_album_cover(album.title, album.artist)
            except Exception as e:
                await message.answer(f"Cover search warning: {e}")

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
        await status_msg.delete()

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

    if callback_data.action == "cancel":
        if os.path.exists(file_path):
            os.remove(file_path)
        await query.message.delete()
        await query.message.answer("Download cancelled.")
        return

    # update msg
    status_suffix = "\n\nApplying tags..." if callback_data.action == "apply" else "\n\nSkipped."
    if query.message.photo:
        await query.message.edit_caption(caption=f"{query.message.caption}{status_suffix}")
    else:
        await query.message.edit_text(text=f"{query.message.text}{status_suffix}")

    if callback_data.action == "apply":
        try:
            await audio_configurator.apply_tags(file_path, track, album, cover_url)
        except Exception as e:
            await query.message.answer(f"Error while applying tags: {e}")

    if os.path.exists(file_path):
        audio_file = FSInputFile(file_path)
        await query.message.answer_audio(audio_file)
        os.remove(file_path)
    else:
        await query.message.answer("File has not been found on server.")

# just for test ; will delete soon
@router.message(F.text)
async def text_handler(message: Message):
    doc = message.text
    await message.answer(f"Text: {doc}")

async def _get_audio(url) -> AudioFile:
    audio_file = await media_installer.download_audio(url)
    if not audio_file: raise Exception("Couldn't download the file.")

    file_path = audio_file.file_path
    if not file_path: raise Exception("Couldn't find the file on server.")

    return audio_file