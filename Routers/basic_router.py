from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

# /start command
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Welcome!")

# just for logging / checking bot status
@router.message(F.text)
async def text_handler(message: Message):
    doc = message.text
    await message.answer(f"Text: {doc}")