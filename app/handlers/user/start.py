from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import get_or_create_user
from app.keyboards.user_kb import main_menu_kb
from app.utils import texts

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    # /start هر فرآیند نیمه‌کاره (خرید، ارسال رسید و ...) را لغو می‌کند
    await state.clear()
    await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        texts.WELCOME.format(name=escape(message.from_user.first_name or "")),
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "🎧 پشتیبانی")
async def support(message: Message) -> None:
    await message.answer(texts.SUPPORT_TEXT.format(support=settings.SUPPORT_USERNAME))
