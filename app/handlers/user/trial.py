from __future__ import annotations

import uuid

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

    # --------------------------------------------------------
    # پیدا کردن / ساخت کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # مقادیر ساده را قبل از commit/rollback ذخیره می‌کنیم
    # تا بعداً باعث MissingGreenlet نشوند.
    user_id = user.id
    telegram_id = user.telegram_id

    # --------------------------------------------------------
    # پیدا کردن پلن‌های تست فعال
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
        "user_id=", user_id,
        "telegram_id=", telegram_id,
        "plans=",
        [
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
            select(UserTrial).where(
                UserTrial.user_id == user_id,
                UserTrial.panel_key == candidate.panel_key,
                UserTrial.used.is_(True),
            )
        )

        already_used = result.scalar_one_or_none()

        print(
            "TRIAL CHECK:",
            "user_id=", user_id,
            "panel=", candidate.panel_key,
            "already_used=", already_used,
        )

        if already_used is None:
            plan = candidate
            break

    # --------------------------------------------------------
    # همه تست‌ها استفاده شده‌اند
    # --------------------------------------------------------

    if plan is None:
        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید."
        )
        return

    # مقادیر ساده پلن را هم ذخیره می‌کنیم
    plan_id = plan.id
    panel_key = plan.panel_key
    plan_name = plan.name

    # --------------------------------------------------------
    # نمایش اطلاعات تست
    # --------------------------------------------------------

    traffic_text = (
        f"{plan.traffic_mb} مگابایت"
        if plan.traffic_mb
        else (
            "نامحدود"
            if plan.traffic_gb <= 0
            else f"{plan.traffic_gb} گیگابایت"
        )
    )

    await message.answer(
        "⏳ در حال ساخت سرویس تست رایگان شما...\n\n"
        f"🌐 سرور: {panel_key}\n"
        f"📦 حجم: {traffic_text}\n"
        f"⏱ مدت: {plan.duration_days} روز"
    )

    # --------------------------------------------------------
    # نام یکتای کانفیگ
    # --------------------------------------------------------

    config_name = (
        f"Trial-{panel_key}-{telegram_id}-{uuid.uuid4().hex[:8]}"
    )

    print(
        "TRIAL CREATE:",
        "user_id=", user_id,
        "panel=", panel_key,
        "config_name=", config_name,
    )

    # --------------------------------------------------------
    # ساخت سفارش
    # --------------------------------------------------------

    order = Order(
        user_id=user_id,
        plan_id=plan_id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=config_name,
    )

    session.add(order)

    await session.commit()
    await session.refresh(order)

    # --------------------------------------------------------
    # relationshipها
    # --------------------------------------------------------

    order.user = user
    order.plan = plan

    # --------------------------------------------------------
    # ساخت کانفیگ روی پنل
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=message.bot,
            session=session,
            order=order,
        )

    except Exception as e:

        # ذخیره مقادیر قبل از rollback انجام شده،
        # بنابراین اینجا دیگر به ORM نیاز نداریم.

        await session.rollback()

        print(
            "TRIAL PROVISION ERROR:",
            f"user={user_id}",
            f"panel={panel_key}",
            f"config={config_name}",
            f"error={e}",
        )

        await message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ساخت موفق بوده است
    # حالا تست را مصرف‌شده ثبت می‌کنیم
    # --------------------------------------------------------

    try:

        trial = UserTrial(
            user_id=user_id,
            panel_key=panel_key,
            used=True,
        )

        session.add(trial)

        await session.commit()

        print(
            "TRIAL CREATED:",
            f"user={user_id}",
            f"panel={panel_key}",
            f"config={config_name}",
        )

    except Exception as e:

        await session.rollback()

        print(
            "TRIAL RECORD ERROR:",
            f"user={user_id}",
            f"panel={panel_key}",
            f"error={e}",
        )
