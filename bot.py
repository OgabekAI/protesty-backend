import asyncio
import os
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart
from aiogram.types import Message

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_SECRET = os.getenv('TELEGRAM_BOT_SECRET', 'your-internal-bot-secret-key')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')

if not BOT_TOKEN:
    print("Xatolik: TELEGRAM_BOT_TOKEN .env faylida topilmadi!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user = message.from_user
    telegram_id = user.id
    first_name = user.first_name or ''

    # Get user profile photo if available
    photo_url = ''
    try:
        user_photos = await bot.get_user_profile_photos(user_id=telegram_id, limit=1)
        if user_photos.total_count > 0:
            file_id = user_photos.photos[0][-1].file_id
            file_info = await bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
    except Exception as e:
        print(f"Profile photo retrieval info: {e}")

    # Request login code from backend API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/auth/telegram/code/",
                headers={
                    "X-Telegram-Bot-Secret": BOT_SECRET
                },
                json={
                    "telegram_id": telegram_id,
                    "telegram_first_name": first_name,
                    "telegram_photo_url": photo_url
                },
                timeout=10.0
            )

            if response.status_code in (200, 201):
                data = response.json()
                code = data.get('code')

                reply_text = (
                    f"Assalomu alaykum, {html.bold(first_name)}! 👋\n\n"
                    f"🔐 Sizning <b>Protesty</b> platformasi uchun bir martalik kirish kodingiz:\n\n"
                    f"<code>{code}</code>\n\n"
                    f"<i>📌 Ushbu 6-xonali kodni vebsaytda kiritib tizimga kiring. Kod 5 daqiqa davomida amal qiladi.</i>"
                )
            else:
                print(f"Backend HTTP error {response.status_code}: {response.text}")
                reply_text = f"⚠️ Xatolik yuz berdi ({response.status_code}). Iltimos, bir ozdan so'ng qayta urinib ko'ring."

        except Exception as err:
            print(f"Connection exception: {err}")
            reply_text = f"❌ Backend serverga ulanishda xatolik: {err}"

    await message.answer(reply_text, parse_mode="HTML")


async def main() -> None:
    print(f"🤖 Telegram Bot aiogram v3 da ishga tushdi...")
    print(f"Bot Username: @{(await bot.get_me()).username}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
