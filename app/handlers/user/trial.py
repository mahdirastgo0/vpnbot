from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import (
    UserTrial,
    Plan,
    Order,
    OrderStatus,
    PaymentMethod,
)

from app.database.crud import get_or_create_user
from app.keyboards.user_kb import BTN_TRIAL
from app.services.delivery import provision_and_deliver


logger = logging.getLogger(__name__)

router = Router(name="trial")

# کاربرانی که ساخت تست برایشان در حال انجام است (جلوگیری از دوبار کلیک)
_in_progress: set[int] = set()


# ============================================================
# HELPERS
# ============================================================

def get_trial_traffic_text(plan: Plan) -> str:

    if plan.traffic_mb:
        return f"{plan.traffic_mb} MB"

    if plan.traffic_gb <= 0:
        return "نامحدود"

    return f"{plan.traffic_gb} GB"


def get_panel_title(panel_key: str) -> str:

    panel = settings.PANELS.get(panel_key)

    return panel.name if panel else f"🌐 {panel_key}"


async def _used_panel_keys(
    session: AsyncSession,
    user_id: int,
) -> set[str]:

    result = await session.execute(
        select(UserTrial.panel_key).where(
            UserTrial.user_id == user_id,
            UserTrial.used.is_(True),
        )
    )

    return set(result.scalars().all())


# ============================================================
# 🎁 سرویس تست رایگان
# ============================================================

@router.message(F.text == BTN_TRIAL)
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
    # پلن‌های تست فعال
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
            "❌ در حال حاضر هیچ سرویس تستی در دسترس نیست."
        )

        return

    # --------------------------------------------------------
    # فقط تست‌هایی که قبلاً مصرف نشده‌اند (یک کوئری برای همه)
    # --------------------------------------------------------

    used = await _used_panel_keys(session, user.id)

    available_plans = [
        plan
        for plan in plans
        if plan.panel_key not in used
    ]

    if not available_plans:

        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید."
        )

        return

    # --------------------------------------------------------
    # ساخت کیبورد انتخاب سرور
    # --------------------------------------------------------

    builder = InlineKeyboardBuilder()

    for plan in available_plans:

        builder.button(
            text=(
                f"{get_panel_title(plan.panel_key)} | "
                f"{get_trial_traffic_text(plan)} | "
                f"{plan.duration_days} روز"
            ),
            callback_data=f"trial_select:{plan.id}",
        )

    builder.adjust(1)

    await message.answer(
        "🎁 <b>سرویس تست رایگان</b>\n\n"
        "هر سرور را فقط یک بار می‌توانید تست کنید.\n\n"
        "👇 لطفاً سرور موردنظر خود را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


# ============================================================
# 🎯 انتخاب سرور تست
# ============================================================

@router.callback_query(F.data.startswith("trial_select:"))
async def select_trial(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(
            "❌ انتخاب نامعتبر است.",
            show_alert=True,
        )
        return

    telegram_id = callback.from_user.id

    if telegram_id in _in_progress:
        await callback.answer("⏳ در حال ساخت سرویس تست شما...")
        return

    user = await get_or_create_user(
        session,
        telegram_id=telegram_id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    # --------------------------------------------------------
    # پلن انتخاب‌شده
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
    # کاربر قبلاً همین پنل را تست کرده؟
    # --------------------------------------------------------

    if plan.panel_key in await _used_panel_keys(session, user.id):
        await callback.answer(
            "❌ شما قبلاً تست این سرور را دریافت کرده‌اید.",
            show_alert=True,
        )
        return

    # پاسخ فوری؛ ساخت روی پنل ممکن است بیش از مهلت callback طول بکشد
    await callback.answer()

    _in_progress.add(telegram_id)

    try:
        await _provision_trial(callback, session, user, plan)
    finally:
        _in_progress.discard(telegram_id)


async def _provision_trial(
    callback: CallbackQuery,
    session: AsyncSession,
    user,
    plan: Plan,
) -> None:

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        "⏳ <b>در حال ساخت سرویس تست شما...</b>\n\n"
        f"🌐 <b>سرور:</b> {escape(get_panel_title(plan.panel_key))}\n"
        f"📦 <b>حجم:</b> {get_trial_traffic_text(plan)}\n"
        f"⏱ <b>مدت:</b> {plan.duration_days} روز",
    )

    # --------------------------------------------------------
    # ساخت Order
    # (شماره سفارش به email پنل اضافه می‌شود تا یکتا باشد)
    # --------------------------------------------------------

    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=f"Trial-{plan.panel_key}-{user.telegram_id}",
    )

    order.user = user
    order.plan = plan

    session.add(order)

    await session.commit()

    # --------------------------------------------------------
    # ساخت سرویس در پنل
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=callback.bot,
            session=session,
            order=order,
        )

    except Exception:

        logger.exception(
            "Trial provision failed: telegram_id=%s order_id=%s plan_id=%s panel=%s",
            user.telegram_id, order.id, plan.id, plan.panel_key,
        )

        await session.rollback()

        # سفارش بدون کانفیگ نباید PAID بماند
        order.status = OrderStatus.CANCELLED
        await session.commit()

        await callback.message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت مصرف تست (فقط وقتی provision موفق شد)
    # --------------------------------------------------------

    try:

        session.add(
            UserTrial(
                user_id=user.id,
                panel_key=plan.panel_key,
                used=True,
            )
        )

        await session.commit()

    except Exception:

        await session.rollback()

        logger.exception(
            "Trial record failed: user_id=%s panel=%s order_id=%s",
            user.id, plan.panel_key, order.id,
        )

        await callback.message.answer(
            "⚠️ سرویس ساخته شد، اما ثبت وضعیت تست با مشکل مواجه شد.\n"
            "لطفاً با پشتیبانی تماس بگیرید."
        )
