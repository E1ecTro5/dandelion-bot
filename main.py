import asyncio
import logging
import os
import command_handler

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN").__str__()
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
        await command_handler.cmd_start(message)

    # /dlp <link>
    @dp.message(Command("dlp"))
    async def handle_dlp(message: Message):
        await command_handler.dlp_handler(message)

    # Message Text handler
    @dp.message(lambda msg: msg.text is not None)
    async def handle_message(message: Message):
        await command_handler.text_handler(message)

    print("Starting the bot...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())