from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Plan
from app.database.crud import get_or_create_user
from app.services.delivery import provision_and_deliver

router = Router(name="trial")


@router.message(F.text == "🎁 سرویس تست رایگان")
async def get_free_trial(
    message: Message,
    session: AsyncSession,
) -> None:

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # قبلاً تست گرفته؟
    if user.trial_used:
        await message.answer(
            "❌ شما قبلاً سرویس تست رایگان خود را دریافت کرده‌اید.\n\n"
            "هر کاربر فقط یک بار می‌تواند از سرویس تست استفاده کند."
        )
        return

    # پیدا کردن پلن تست
    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .limit(1)
    )

    plan = result.scalar_one_or_none()

    if plan is None:
        await message.answer(
            "❌ در حال حاضر سرویس تست رایگان در دسترس نیست."
        )
        return

    # جلوگیری از درخواست همزمان / دوباره
    user.trial_used = True
    await session.commit()

    # ساخت سفارش رایگان
    from app.database.models import (
        Order,
        OrderStatus,
        PaymentMethod,
    )

    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=f"Trial-{message.from_user.id}",
    )

    session.add(order)
    await session.commit()
    await session.refresh(order)

    # بارگذاری relationshipها
    result = await session.execute(
        select(Order)
        .where(Order.id == order.id)
    )

    order = result.scalar_one()

    # relationshipها را دستی بارگذاری می‌کنیم
    order.plan = plan
    order.user = user

    try:
        await provision_and_deliver(
            message.bot,
            session,
            order,
        )

    except Exception:
        # اگر ساخت کانفیگ شکست خورد، امکان دریافت مجدد را آزاد کن
        user.trial_used = False
        await session.commit()

        await message.answer(
            "⚠️ در ساخت سرویس تست مشکلی پیش آمد.\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )