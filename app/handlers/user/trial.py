from __future__ import annotations

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
# 🎁 نمایش سرویس‌های تست
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

    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
    )

    plans = list(result.scalars().all())

    print(
        "TRIAL DEBUG:",
        "user_id=", user.id,
        "telegram_id=", user.telegram_id,
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
    # فقط تست‌هایی که کاربر هنوز استفاده نکرده
    # --------------------------------------------------------

    available_plans = []

    for plan in plans:

        result = await session.execute(
            select(UserTrial).where(
                UserTrial.user_id == user.id,
                UserTrial.panel_key == plan.panel_key,
                UserTrial.used.is_(True),
            )
        )

        already_used = result.scalar_one_or_none()

        print(
            "TRIAL CHECK:",
            "user_id=", user.id,
            "panel=", plan.panel_key,
            "already_used=", already_used,
        )

        if already_used is None:
            available_plans.append(plan)

    # --------------------------------------------------------
    # اگر هیچ تستی باقی نمانده
    # --------------------------------------------------------

    if not available_plans:
        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید."
        )
        return

    # --------------------------------------------------------
    # نمایش انتخاب سرور به کاربر
    # --------------------------------------------------------

    builder = InlineKeyboardBuilder()

    for plan in available_plans:

        if plan.panel_key == "ir1":
            title = "🇮🇷 ایران - تانل"
        elif plan.panel_key == "pol":
            title = "🇵🇱 لهستان - مستقیم"
        else:
            title = f"🌐 {plan.panel_key}"

        traffic = (
            f"{plan.traffic_mb} MB"
            if plan.traffic_mb
            else (
                "نامحدود"
                if plan.traffic_gb <= 0
                else f"{plan.traffic_gb} GB"
            )
        )

        builder.button(
            text=f"{title} | {traffic} | {plan.duration_days} روز",
            callback_data=f"trial_select:{plan.id}",
        )

    builder.adjust(1)

    await message.answer(
        "🎁 <b>انتخاب سرویس تست رایگان</b>\n\n"
        "لطفاً سروری که می‌خواهید تست کنید را انتخاب کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ============================================================
# 🎯 انتخاب سرویس تست توسط کاربر
# ============================================================

@router.callback_query(F.data.startswith("trial_select:"))
async def select_trial(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer(
            "❌ انتخاب نامعتبر است.",
            show_alert=True,
        )
        return

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

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
        await callback.answer(
            "❌ این سرویس تست دیگر در دسترس نیست.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # بررسی اینکه همین پنل قبلاً استفاده شده یا نه
    # --------------------------------------------------------

    result = await session.execute(
        select(UserTrial).where(
            UserTrial.user_id == user.id,
            UserTrial.panel_key == plan.panel_key,
            UserTrial.used.is_(True),
        )
    )

    already_used = result.scalar_one_or_none()

    if already_used is not None:
        await callback.answer(
            "❌ شما قبلاً تست این سرور را دریافت کرده‌اید.",
            show_alert=True,
        )
        return

    await callback.answer()

    # --------------------------------------------------------
    # حذف پیام انتخاب
    # --------------------------------------------------------

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # --------------------------------------------------------
    # اطلاع به کاربر
    # --------------------------------------------------------

    traffic = (
        f"{plan.traffic_mb} MB"
        if plan.traffic_mb
        else (
            "نامحدود"
            if plan.traffic_gb <= 0
            else f"{plan.traffic_gb} GB"
        )
    )

    await callback.message.answer(
        "⏳ <b>در حال ساخت سرویس تست شما...</b>\n\n"
        f"🌐 سرور: {plan.panel_key}\n"
        f"📦 حجم: {traffic}\n"
        f"⏱ مدت: {plan.duration_days} روز",
        parse_mode="HTML",
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
        config_name=f"Trial-{plan.panel_key}-{callback.from_user.id}",
    )

    session.add(order)

    await session.commit()
    await session.refresh(order)

    # --------------------------------------------------------
    # جلوگیری از Lazy Loading
    # --------------------------------------------------------

    order.user = user
    order.plan = plan

    # --------------------------------------------------------
    # ساخت کانفیگ
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=callback.bot,
            session=session,
            order=order,
        )

    except Exception as e:

        print(
            "TRIAL PROVISION ERROR:",
            f"user={user.id}",
            f"panel={plan.panel_key}",
            f"error={e}",
        )

        await session.rollback()

        await callback.message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت مصرف تست
    # --------------------------------------------------------

    trial = UserTrial(
        user_id=user.id,
        panel_key=plan.panel_key,
        used=True,
    )

    session.add(trial)

    await session.commit()

    print(
        "TRIAL CREATED:",
        f"user={user.id}",
        f"panel={plan.panel_key}",
    )

