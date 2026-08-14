import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
import os
from dotenv import load_dotenv

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
            file_path = media_info.get("file_path")

            audio_file = FSInputFile(file_path)
            await message.answer(f"Found: {media_info.get('title')} by {media_info.get('artist')}")
            await message.answer_audio(audio_file)

            # here we can put the file configurator methods in future

            # deleting after sending
            if os.path.exists(file_path):
                os.remove(file_path)

        except Exception as e:
            logging.error(f"Error during download: {e}")
            await message.answer("Error during download.")
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