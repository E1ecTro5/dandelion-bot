import os
from Utils import audio_configurator, media_installer
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from Models.file_model import AudioFile
from Models.main_models import Album, Track

# create router to pass in the main.py
router = Router()

# temp storage ; how about you just use Redis in future instead of this?
PENDING_DOWNLOADS = {}

class ConfirmAction(CallbackData, prefix="confirm_dl"):
    action: str # action type
    download_id: str

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Welcome!")

@router.message(Command("dlp"))
async def dlp_handler(message: Message):
    status_msg = None
    try:
        url = await _check_url(message.text)
        status_msg = await message.answer("Downloading...")
        audio_file = await _get_audio(url)

        file = await _track_from_audio(audio_file)
        await message.answer(f"Downloaded: {file.title} by {file.artists}") # just to log

        # tags
        try: track, album = await audio_configurator.setup_tags(audio_file)
        except Exception as e:
            await message.answer(f"Tag setup failed: {e}")
            track = file
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
        if status_msg: await status_msg.delete()

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

# just for test ; will delete soon
@router.message(F.text)
async def text_handler(message: Message):
    doc = message.text
    await message.answer(f"Text: {doc}")

# ----- helper methods here ------

async def _check_url(url: str | None) -> str:
    if url is None: raise Exception("Null url.")
    args = url.split(maxsplit=1)
    if len(args) < 2: raise Exception("Please enter a valid URL. Use /dlp <URL>")

    return args[1]

async def _get_audio(url) -> AudioFile:
    audio_file = await media_installer.download_audio(url)
    if not audio_file: raise Exception("Couldn't download the file.")

    file_path = audio_file.file_path
    if not file_path: raise Exception("Couldn't find the file on server.")

    return audio_file

async def _track_from_audio(file: AudioFile) -> Track:
    track = Track(
        title=file.title,
        artists=file.artist.split(", ")[0] if file.artist else None,
        file_path=file.file_path
    )

    return track

async def _set_album_cover(album: Album) -> str | None:
    if album.title and album.artist:
        album_cover = await audio_configurator.get_album_cover(album.title, album.artist)
        return album_cover

    return None

async def _generate_caption_text(album: Album, track: Track) -> str:
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