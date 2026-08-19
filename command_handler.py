import os
import audio_configurator
import media_installer
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

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
        media_info = await media_installer.download_audio(url)
        if not media_info:
            await message.answer("Couldn't download the file.")
            return

        file_path = media_info.get("file_path")
        if not file_path:
            await message.answer("Couldn't find the file on server.")
            return

        audio_file = FSInputFile(file_path)

        track_name = media_info.get('title')
        artist_name = str(media_info.get('artist')).split(", ")[0]
        await message.answer(f"Found: {track_name} by {artist_name}")

        tags = None

        try:
            tags = await audio_configurator.setup_tags(artist_name, track_name)
        except Exception as e:
            await message.answer(e.__str__())

        if tags:
            album_title = tags.get("album", "")
            album_artist = tags.get("album_artist", artist_name)
            track_title = tags.get("title", track_name)
            artists = tags.get("artists", "error")
            year = tags.get("year", "")
            genres = ", ".join(tags.get("genres", []))
            disk_number = tags.get("disc_number") or tags.get("disk_number", "1")
            disk_position = tags.get("track_number", "1")
            basic_position = tags.get("position", "")

            album_cover = None

            try:
                album_cover = await audio_configurator.get_cover_from_itunes(album_artist, album_title)
            except Exception as e:
                await message.answer(e.__str__())

            caption_text = (
                f"Album: {album_title}\n"
                f"Album Artist: {album_artist}\n"
                f"Year: {year}\n"
                f"Genres: {genres}\n\n"
                
                f"Track: {track_title}\n"
                f"Artists: {artists}\n"
                f"Disk number: {disk_number}\n"
                f"Disk position: {disk_position}\n"
                f"Basic position: {basic_position}"
            )

            # unique download id
            download_id = str(uuid.uuid4())[:8]
            PENDING_DOWNLOADS[download_id] = {
                "file_path": file_path,
                "tags": tags,
                "cover_url": album_cover
            }

            # inline keyboard
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
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await message.answer(caption_text, reply_markup=keyboard)
            else:
                await message.answer(caption_text, reply_markup=keyboard)
        # else:
        #     await message.answer("Tags in Discogs has not been found...")

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
    tags = data["tags"]
    cover_url = data["cover_url"]

    if callback_data.action == "cancel":
        if os.path.exists(file_path):
            os.remove(file_path)

        await query.message.delete()
        await query.message.answer("Download cancelled.")
        return

    if callback_data.action == "apply" and tags:
        await query.message.edit_caption(caption=f"{query.message.caption}\n\nApplying tags..")
        try:
            await audio_configurator.apply_tags(file_path, tags, cover_url)
        except Exception as e:
            await query.message.answer(f"Error while applying tags: {e}")
    else:
        await query.message.edit_caption(caption=f"{query.message.caption}\n\nSkipped.")

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