import os
import audio_configurator
import media_installer

from aiogram.types import Message, FSInputFile

async def cmd_start(message: Message):
    await message.answer("Welcome!")

async def text_handler(message: Message):
    doc = message.text
    await message.answer(f"Text: {doc}")

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

            if album_cover:
                try:
                    await message.answer_photo(
                        photo=album_cover,
                        caption=caption_text
                    )
                except Exception as e:
                    await message.answer(caption_text)
            else:
                await message.answer(caption_text)
        else:
            await message.answer("Tags in Discogs has not been found...")

        await message.answer_audio(audio_file)

        # deleting after sending
        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        await message.answer(f"Error during download: {e}")
    finally:
        await status_msg.delete()