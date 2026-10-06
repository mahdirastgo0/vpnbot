import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.middlewares.admin_filter import IsAdmin
from app.states.user_states import AdminBroadcast

router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PROMPT = "پیامی که می‌خوای برای همه کاربرها ارسال بشه رو بفرست:"


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminBroadcast.waiting_message)
    await message.answer(PROMPT)


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcast.waiting_message)
    await callback.message.answer(PROMPT)
    await callback.answer()


@router.message(AdminBroadcast.waiting_message)
async def broadcast_send(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    await state.clear()
    result = await session.execute(select(User.telegram_id).where(User.is_blocked.is_(False)))
    user_ids = list(result.scalars().all())

    sent, failed = 0, 0
    blocked: list[int] = []
    status_msg = await message.answer(f"در حال ارسال به {len(user_ids)} کاربر...")
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await message.copy_to(chat_id=uid)
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            blocked.append(uid)
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # جلوگیری از محدودیت نرخ تلگرام

    # کاربرانی که ربات را بلاک کرده‌اند دفعه بعد ارسال نمی‌شوند
    if blocked:
        await session.execute(
            update(User).where(User.telegram_id.in_(blocked)).values(is_blocked=True)
        )
        await session.commit()

    await status_msg.edit_text(f"✅ ارسال شد به {sent} کاربر. ({failed} ناموفق)")
