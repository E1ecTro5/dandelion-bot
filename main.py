import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
import os
from dotenv import load_dotenv

import audio_configurator
import media_installer

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081")

logging.basicConfig(level=logging.INFO)

async def main():
    custom_server = TelegramAPIServer.from_base('http://telegram-bot-api:8081')
    session = AiohttpSession(api=custom_server)

    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    # /start handler
    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        await message.answer("HI THERE!")

    @dp.message(Command("dlp"))
    async def handle_dlp(message: Message):
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
            artist_name = media_info.get('artist')
            await message.answer(f"Found: {track_name} by {artist_name}")

            tags = None

            try:
                tags = await audio_configurator.setup_tags(artist_name, track_name)
            except Exception as e:
                await message.answer(e.__str__())

            if tags:
                album_title = tags.get("album", "")
                artist_title = tags.get("artist", artist_name)
                track_title = tags.get("title", track_name)
                year = tags.get("year", "")
                genres = ", ".join(tags.get("genres", []))
                disk_number = tags.get("disc_number") or tags.get("disk_number", "1")
                disk_position = tags.get("track_number", "1")
                basic_position = tags.get("position", "")

                album_cover = None

                try:
                    album_cover = await audio_configurator.get_cover_from_itunes(artist_title, album_title)
                except Exception as e:
                    logging.warning(f"Failed to send photo from URL ({e}), falling back to text.")
                    await message.answer(e)

                caption_text = (
                    f"Album: {album_title}\n"
                    f"Track: {track_title}\n"
                    f"Artist: {artist_title}\n"
                    f"Year: {year}\n"
                    f"Genres: {genres}\n"
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
                        logging.warning(f"Failed to send photo from URL ({e}), falling back to text.")
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
            logging.error(f"Error during download: {e}")
            await message.answer(f"Error during download: {e}")
        finally:
            await status_msg.delete()

    # Message Text handler
    @dp.message(lambda msg: msg.text is not None)
    async def handle_message(message: Message):
        doc = message.text
        await message.answer(f"Text: {doc}")

    print("Starting the bot...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())