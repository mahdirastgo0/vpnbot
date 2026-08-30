from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Plan, PaymentMethod, OrderStatus
from app.database.crud import get_plan, get_or_create_user, create_order
from app.keyboards.user_kb import (
    panels_kb,
    plans_kb,
    payment_methods_kb,
    config_name_kb,
)
from app.states.buy import BuyFlow
from app.utils import texts
from app.services.delivery import provision_and_deliver


router = Router(name="user_buy")

# ============================================================
# 🛒 خرید سرویس
# ============================================================

@router.message(F.text == "🛒 خرید سرویس")
async def buy_service(
    message: Message,
    state: FSMContext,
) -> None:

    await state.clear()

    if not settings.PANELS:
        await message.answer(
            "❌ در حال حاضر هیچ سروری برای فروش فعال نیست."
        )
        return

    await message.answer(
        "🌐 سرور مورد نظر خود را انتخاب کنید:",
        reply_markup=panels_kb(),
    )


# ============================================================
# انتخاب پنل
# ============================================================

@router.callback_query(F.data.startswith("panel:"))
async def select_panel(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    panel_key = callback.data.split(":", 1)[1]

    if panel_key not in settings.PANELS:
        await callback.answer(
            "❌ سرور پیدا نشد.",
            show_alert=True,
        )
        return

    result = await session.execute(
        select(Plan)
        .where(
            Plan.panel_key == panel_key,
            Plan.is_active.is_(True),
            Plan.is_trial.is_(False),
        )
        .order_by(Plan.id.asc())
    )

    plans = list(result.scalars().all())

    if not plans:
        await callback.message.edit_text(
            "❌ برای این سرور در حال حاضر پلنی موجود نیست."
        )
        await callback.answer()
        return

    panel = settings.PANELS[panel_key]

    await callback.message.edit_text(
        f"🌐 سرور: {panel.name}\n\n"
        f"📦 پلن مورد نظر خود را انتخاب کنید:",
        reply_markup=plans_kb(
            panel_key,
            plans,
        ),
    )

    await callback.answer()


# ============================================================
# انتخاب پلن
# ============================================================

@router.callback_query(F.data.startswith("plan:"))
async def select_plan(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    try:
        plan_id = int(
            callback.data.split(":", 1)[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "❌ پلن نامعتبر است.",
            show_alert=True,
        )
        return

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is None or not plan.is_active:
        await callback.answer(
            "❌ این پلن دیگر موجود نیست.",
            show_alert=True,
        )
        return

    if plan.panel_key not in settings.PANELS:
        await callback.answer(
            "❌ سرور این پلن در دسترس نیست.",
            show_alert=True,
        )
        return

    await state.clear()

    await state.update_data(
        plan_id=plan.id,
    )

    await state.set_state(
        BuyFlow.waiting_config_name
    )

    await callback.message.edit_text(
        texts.CONFIG_NAME_REQUEST,
        reply_markup=config_name_kb(),
    )

    await callback.answer()


# ============================================================
# دریافت نام کانفیگ
# ============================================================

@router.message(
    BuyFlow.waiting_config_name,
    F.text,
)
async def receive_config_name(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    name = message.text.strip()

    if not name:
        await message.answer(
            "❌ اسم کانفیگ نمی‌تواند خالی باشد."
        )
        return

    if len(name) > 128:
        await message.answer(
            "❌ اسم کانفیگ حداکثر ۱۲۸ کاراکتر باشد."
        )
        return

    data = await state.get_data()

    plan_id = data.get("plan_id")

    if not plan_id:
        await state.clear()

        await message.answer(
            "❌ اطلاعات خرید پیدا نشد.\n"
            "لطفاً دوباره از «🛒 خرید سرویس» شروع کن."
        )
        return

    plan = await get_plan(
        session,
        int(plan_id),
    )

    if plan is None or not plan.is_active:
        await state.clear()

        await message.answer(
            "❌ این پلن دیگر موجود نیست."
        )
        return

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        await state.clear()

        await message.answer(
            "❌ سرور این پلن پیدا نشد."
        )
        return

    await state.update_data(
        config_name=name,
    )

    traffic = (
        "نامحدود"
        if plan.traffic_gb <= 0
        else f"{plan.traffic_gb} گیگ"
    )

    plan_type = getattr(
        plan.plan_type,
        "value",
        str(plan.plan_type),
    )

    plan_type_labels = {
        "DIRECT": "⚡️ مستقیم",
        "TUNNEL": "🚇 تانل",
    }

    summary = texts.ORDER_SUMMARY.format(
        panel_name=panel.name,
        plan_type=plan_type_labels.get(
            plan_type,
            plan_type,
        ),
        plan_name=plan.name,
        duration=plan.duration_days,
        traffic=traffic,
        amount=plan.price,
        currency=settings.CURRENCY_LABEL,
    )

    await message.answer(
        summary
        + "\n\n"
        + texts.CHOOSE_PAYMENT,
        reply_markup=payment_methods_kb(
            plan.id
        ),
    )


# ============================================================
# اسم تصادفی
# ============================================================

@router.callback_query(
    F.data == "config_name_random"
)
async def random_config_name(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    import secrets

    random_name = (
        f"VPN-"
        f"{secrets.token_hex(4).upper()}"
    )

    await state.update_data(
        config_name=random_name,
    )

    await callback.message.edit_text(
        f"📱 نام کانفیگ:\n\n"
        f"`{random_name}`\n\n"
        f"💳 روش پرداخت را انتخاب کنید.",
        reply_markup=None,
        parse_mode="Markdown",
    )

    data = await state.get_data()
    plan_id = data.get("plan_id")

    if plan_id:
        await callback.message.edit_reply_markup(
            reply_markup=payment_methods_kb(
                int(plan_id)
            )
        )

    await callback.answer()


# ============================================================
# لغو خرید
# ============================================================

@router.callback_query(
    F.data.in_({
        "config_name_cancel",
        "buy_cancel",
    })
)
async def cancel_buy(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.clear()

    await callback.message.edit_text(
        "❌ خرید لغو شد."
    )

    await callback.answer()


# ============================================================
# بازگشت به پنل‌ها
# ============================================================

@router.callback_query(
    F.data == "back_to_panels"
)
async def back_to_panels(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.clear()

    await callback.message.edit_text(
        "🌐 سرور مورد نظر خود را انتخاب کنید:",
        reply_markup=panels_kb(),
    )

    await callback.answer()


# ============================================================
# دکمه‌های بدون عملکرد
# ============================================================

@router.callback_query(
    F.data == "noop"
)
async def noop(
    callback: CallbackQuery,
) -> None:

    await callback.answer()