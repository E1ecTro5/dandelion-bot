import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Message
from aiogram.filters import Command
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL")

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