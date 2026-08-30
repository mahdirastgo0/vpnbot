from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    User,
    UserTrial,
    Plan,
    Order,
    OrderStatus,
    PaymentMethod,
)
from app.database.crud import get_or_create_user
from app.services.delivery import provision_and_deliver


router = Router(name="trial")


# ============================================================
# 🎁 سرویس تست رایگان
# ============================================================

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

    # --------------------------------------------------------
    # پیدا کردن اولین پلن تست فعال
    # --------------------------------------------------------

    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
    )

    plans = result.scalars().all()

    print(
    "TRIAL DEBUG:",
    "user_id=", user.id,
    "telegram_id=", user.telegram_id,
    "plans=", [
        (
            p.id,
            p.panel_key,
            p.is_trial,
            p.is_active,
        )
        for p in plans
    ],
)

    if not plans:
        await message.answer(
            "❌ در حال حاضر هیچ سرویس تستی در دسترس نیست."
        )
        return

    # --------------------------------------------------------
    # پیدا کردن اولین پنلی که کاربر هنوز تست آن را نگرفته
    # --------------------------------------------------------

    plan = None

    for candidate in plans:

        result = await session.execute(
            select(UserTrial)
            .where(
                UserTrial.user_id == user.id,
                UserTrial.panel_key == candidate.panel_key,
                UserTrial.used.is_(True),
            )
        )

        already_used = result.scalar_one_or_none()

        print(
            "TRIAL CHECK:",
            "user_id=", user.id,
            "panel=", candidate.panel_key,
            "already_used=", already_used,
        )

        if already_used is None:
            plan = candidate
            break

    # --------------------------------------------------------
    # همه تست‌ها قبلاً استفاده شده‌اند
    # --------------------------------------------------------

    if plan is None:
        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید."
        )
        return

    # --------------------------------------------------------
    # نمایش اطلاعات تست
    # --------------------------------------------------------

    await message.answer(
        "⏳ در حال ساخت سرویس تست رایگان شما...\n\n"
        f"🌐 سرور: {plan.panel_key}\n"
        f"📦 حجم: {plan.traffic_gb} گیگابایت\n"
        f"⏱ مدت: {plan.duration_days} روز"
    )

    # --------------------------------------------------------
    # ساخت سفارش
    # --------------------------------------------------------

    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=f"Trial-{plan.panel_key}-{message.from_user.id}",
    )

    session.add(order)
    await session.commit()
    await session.refresh(order)

    # relationshipها
    order.user = user
    order.plan = plan

    # --------------------------------------------------------
    # ساخت کانفیگ
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=message.bot,
            session=session,
            order=order,
        )

    except Exception as e:

        await session.rollback()

        print(
            f"TRIAL PROVISION ERROR "
            f"user={user.id} "
            f"panel={plan.panel_key}: {e}"
        )

        await message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت اینکه کاربر تست این پنل را مصرف کرده
    # --------------------------------------------------------

    trial = UserTrial(
        user_id=user.id,
        panel_key=plan.panel_key,
        used=True,
    )

    session.add(trial)
    await session.commit()

    print(
        f"TRIAL CREATED "
        f"user={user.id} "
        f"panel={plan.panel_key}"
    )