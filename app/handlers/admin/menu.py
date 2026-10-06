from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards.admin_kb import admin_main_kb
from app.middlewares.admin_filter import IsAdmin

router = Router(name="admin_menu")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

HELP_TEXT = (
    "🛠 پنل مدیریت\n\n"
    "از منوی زیر می‌توانید سرویس‌ها، سفارش‌ها و کاربران را مدیریت کنید.\n\n"
    "/addplan — افزودن پلن جدید\n"
    "/plans — لیست پلن‌ها\n"
    "/delplan &lt;id&gt; — غیرفعال کردن پلن\n"
    "/pending — سفارش‌های در انتظار تایید\n"
    "/broadcast — ارسال پیام همگانی"
)


@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=admin_main_kb())


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(HELP_TEXT, reply_markup=admin_main_kb())
    await callback.answer()
