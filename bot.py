import asyncio
import os
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_SECRET = os.getenv('TELEGRAM_BOT_SECRET')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:8000')

ADMIN_TELEGRAM_IDS = [
    int(x.strip()) for x in os.getenv('ADMIN_TELEGRAM_IDS', '').split(',') if x.strip().isdigit()
]

if not BOT_TOKEN:
    print("Xatolik: TELEGRAM_BOT_TOKEN .env faylida topilmadi!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_TELEGRAM_IDS


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user = message.from_user
    telegram_id = user.id
    first_name = user.first_name or ''
    username = user.username or ''

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
                    "telegram_username": username,
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


@dp.message(Command("ad", "broadcast"))
@dp.message(F.caption.startswith("/ad") | F.caption.startswith("/broadcast"))
async def broadcast_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    text = ''
    photo_file_id = None

    # Check if replied to another message
    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.photo:
            photo_file_id = replied.photo[-1].file_id
            text = replied.caption or replied.text or ''
        elif replied.text:
            text = replied.text
    # Check if this message has photo
    elif message.photo:
        photo_file_id = message.photo[-1].file_id
        caption = message.caption or ''
        # Strip /ad or /broadcast from caption
        for cmd in ['/ad', '/broadcast']:
            if caption.startswith(cmd):
                text = caption[len(cmd):].strip()
                break
    # Direct text command
    elif message.text:
        full_text = message.text
        for cmd in ['/ad', '/broadcast']:
            if full_text.startswith(cmd):
                text = full_text[len(cmd):].strip()
                break

    if not text and not photo_file_id:
        usage_text = (
            "📢 <b>Reklama / E'lon yuborish yo'riqnomasi:</b>\n\n"
            "1️⃣ <b>Matnli reklama:</b>\n<code>/ad Reklama matni shu yerda...</code>\n\n"
            "2️⃣ <b>Rasmli reklama:</b>\nRasm yuklab, izohiga <code>/ad Reklama matni</code> deb yozing.\n\n"
            "3️⃣ <b>Xabarga javob berish:</b>\nIstalgan rasm yoki matnli xabarga <code>/ad</code> deb reply qiling."
        )
        await message.answer(usage_text, parse_mode="HTML")
        return

    status_msg = await message.answer("🔄 Reklama foydalanuvchilarga yuborilmoqda, iltimos kuting...")

    photo_url = photo_file_id or ''

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/auth/telegram/broadcast/",
                headers={"X-Telegram-Bot-Secret": BOT_SECRET},
                json={
                    "text": text,
                    "photo_url": photo_url
                },
                timeout=60.0
            )

            if response.status_code == 200:
                result = response.json()
                total = result.get('total', 0)
                sent = result.get('sent', 0)
                failed = result.get('failed', 0)

                result_text = (
                    f"✅ <b>Reklama muvaffaqiyatli tarqatildi!</b>\n\n"
                    f"👥 Jami mo'ljallangan: <b>{total}</b>\n"
                    f"🚀 Yetkazildi: <b>{sent}</b>\n"
                    f"❌ Xatolik / Bloklangan: <b>{failed}</b>"
                )
            else:
                result_text = f"⚠️ Xatolik yuz berdi ({response.status_code}): {response.text}"
        except Exception as err:
            result_text = f"❌ Serverga ulanishda xatolik: {err}"

    await status_msg.edit_text(result_text, parse_mode="HTML")


async def main() -> None:
    print(f"🤖 Telegram Bot aiogram v3 da ishga tushdi...")
    print(f"Bot Username: @{(await bot.get_me()).username}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
