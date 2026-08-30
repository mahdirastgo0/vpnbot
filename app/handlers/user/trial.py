from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
# 🎁 نمایش تست‌های رایگان
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

    user_id = user.id

    # --------------------------------------------------------
    # پیدا کردن تمام پلن‌های تست فعال
    # --------------------------------------------------------

    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
    )

    plans = list(result.scalars().all())

    if not plans:
        await message.answer(
            "❌ در حال حاضر هیچ سرویس تست رایگانی در دسترس نیست."
        )
        return

    # --------------------------------------------------------
    # ساخت دکمه‌ها
    # --------------------------------------------------------

    builder = InlineKeyboardBuilder()

    for plan in plans:

        # نام نمایشی سرور
        if plan.panel_key == "ir1":
            server_name = "🇮🇷 ایران - تانل"

        elif plan.panel_key == "pol":
            server_name = "🇵🇱 لهستان - مستقیم"

        else:
            server_name = f"🌐 {plan.panel_key}"

        # حجم
        if plan.traffic_mb:
            traffic = f"{plan.traffic_mb} MB"
        elif plan.traffic_gb > 0:
            traffic = f"{plan.traffic_gb} GB"
        else:
            traffic = "نامحدود"

        builder.button(
            text=f"{server_name} | {traffic} | {plan.duration_days} روز",
            callback_data=f"trial:{plan.id}",
        )

    builder.adjust(1)

    await message.answer(
        "🎁 <b>سرویس تست رایگان</b>\n\n"
        "سرور موردنظر خود را برای تست انتخاب کنید:\n\n"
        "هر سرور را فقط یک بار می‌توانید تست کنید.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


# ============================================================
# 🎯 انتخاب تست توسط کاربر
# ============================================================

@router.callback_query(F.data.startswith("trial:"))
async def select_trial(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    await callback.answer()

    # --------------------------------------------------------
    # دریافت plan_id
    # --------------------------------------------------------

    try:
        plan_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.message.answer(
            "❌ درخواست نامعتبر است."
        )
        return

    # --------------------------------------------------------
    # پیدا کردن کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    user_id = user.id
    telegram_id = user.telegram_id

    # --------------------------------------------------------
    # پیدا کردن پلن انتخاب‌شده
    # --------------------------------------------------------

    result = await session.execute(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
    )

    plan = result.scalar_one_or_none()

    if plan is None:
        await callback.message.answer(
            "❌ این سرویس تست دیگر در دسترس نیست."
        )
        return

    panel_key = plan.panel_key
    plan_name = plan.name

    # --------------------------------------------------------
    # بررسی اینکه کاربر قبلاً همین سرور را تست کرده یا نه
    # --------------------------------------------------------

    result = await session.execute(
        select(UserTrial).where(
            UserTrial.user_id == user_id,
            UserTrial.panel_key == panel_key,
            UserTrial.used.is_(True),
        )
    )

    already_used = result.scalar_one_or_none()

    print(
        "TRIAL SELECT:",
        "user_id=", user_id,
        "plan_id=", plan_id,
        "panel=", panel_key,
        "already_used=", already_used,
    )

    if already_used is not None:
        await callback.message.answer(
            f"❌ شما قبلاً سرویس تست سرور {panel_key} را دریافت کرده‌اید.\n\n"
            "می‌توانید سرور دیگری را برای تست انتخاب کنید."
        )
        return

    # --------------------------------------------------------
    # نمایش وضعیت
    # --------------------------------------------------------

    if plan.traffic_mb:
        traffic_text = f"{plan.traffic_mb} مگابایت"
    elif plan.traffic_gb > 0:
        traffic_text = f"{plan.traffic_gb} گیگابایت"
    else:
        traffic_text = "نامحدود"

    await callback.message.answer(
        "⏳ <b>در حال ساخت سرویس تست شما...</b>\n\n"
        f"🌐 سرور: {panel_key}\n"
        f"📦 حجم: {traffic_text}\n"
        f"⏱ مدت: {plan.duration_days} روز",
        parse_mode="HTML",
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
    # Relationshipها را دستی تنظیم می‌کنیم
    # --------------------------------------------------------

    order.user = user
    order.plan = plan

    # --------------------------------------------------------
    # ساخت کانفیگ روی پنل
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=callback.bot,
            session=session,
            order=order,
        )

    except Exception as e:

        await session.rollback()

        print(
            "TRIAL PROVISION ERROR:",
            f"user={user_id}",
            f"panel={panel_key}",
            f"plan={plan_name}",
            f"config={config_name}",
            f"error={e}",
        )

        await callback.message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت مصرف تست
    # فقط بعد از موفقیت ساخت کانفیگ
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
