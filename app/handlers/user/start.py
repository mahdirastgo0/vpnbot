from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import get_or_create_user
from app.keyboards.user_kb import main_menu_kb
from app.utils import texts

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        texts.WELCOME.format(name=message.from_user.first_name),
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "🎧 پشتیبانی")
async def support(message: Message) -> None:
    from app.config import settings

    await message.answer(texts.SUPPORT_TEXT.format(support=settings.SUPPORT_USERNAME))
