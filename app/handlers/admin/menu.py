from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.keyboards.admin_kb import admin_main_kb
from app.middlewares.admin_filter import IsAdmin

router = Router(name="admin_menu")
router.message.filter(IsAdmin())

HELP_TEXT = (
    "🛠 پنل مدیریت\n\n"
    "/addplan — افزودن پلن جدید\n"
    "/plans — لیست پلن‌های فعال\n"
    "/delplan <id> — غیرفعال کردن پلن\n"
    "/pending — سفارش‌های در انتظار تایید\n"
    "/broadcast — ارسال پیام همگانی\n"
)


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=admin_main_kb())
