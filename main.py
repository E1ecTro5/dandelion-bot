import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv
from Routers import basic_router, audio_router

load_dotenv() # detects the .env file

BOT_TOKEN = os.getenv("BOT_TOKEN").__str__() # your telegram bot token
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://localhost:8081") # local telegram app server

logging.basicConfig(level=logging.INFO) # basic logging

async def main():
    custom_server = TelegramAPIServer.from_base('http://telegram-bot-api:8081') # connect to local server (from Docker)
    session = AiohttpSession(api=custom_server) # custom Aiohttp session, to make bot call to our local server, not the official one

    bot = Bot(token=BOT_TOKEN, session=session) # telegram bot
    dp = Dispatcher() # main manager for routing messages and commands (сообщения, команды)

    dp.include_router(basic_router.router) # basic router ("/start" and "{text}")
    dp.include_router(audio_router.router) # audio router ("/dlp")

    print("Starting the bot...")

    try:
        await dp.start_polling(bot) # infinite loop, long polling, update cycle
    finally:
        await bot.session.close() # close bot's session

if __name__ == "__main__":
    asyncio.run(main()) # async run main function