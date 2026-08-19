from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import create_order, get_plan
from app.database.models import PaymentMethod
from app.keyboards.payment_kb import payment_methods_kb
from app.keyboards.user_kb import config_name_kb
from app.services.zarinpal import zarinpal
from app.states.buy import BuyFlow
from app.utils import texts


router = Router(name="user_buy")


PLAN_TYPE_LABELS = {
    "DIRECT": "🌍 مستقیم",
    "TUNNEL": "🇮🇷 تانل",
}


# ==========================================================
# انتخاب پلن
# ==========================================================

@router.callback_query(F.data.startswith("buy_plan:"))
async def choose_plan(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = int(callback.data.split(":", 1)[1])

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is None or not plan.is_active:
        await callback.answer(
            "این پلن دیگر موجود نیست.",
            show_alert=True,
        )
        return

    # ذخیره پلن انتخاب‌شده
    await state.update_data(
        plan_id=plan.id,
    )

    # رفتن به مرحله دریافت نام کانفیگ
    await state.set_state(
        BuyFlow.waiting_config_name
    )

    await callback.message.edit_text(
        texts.CONFIG_NAME_REQUEST,
        reply_markup=config_name_kb(),
    )

    await callback.answer()


# ==========================================================
# دریافت اسم کانفیگ
# ==========================================================

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
            "❌ سفارش پیدا نشد.\n"
            "دوباره از خرید سرویس شروع کن."
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

    # ذخیره نام کانفیگ
    await state.update_data(
        config_name=name,
    )

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        await state.clear()

        await message.answer(
            "❌ پنل مربوط به این پلن پیدا نشد."
        )
        return

    plan_type = PLAN_TYPE_LABELS.get(
        plan.plan_type,
        plan.plan_type,
    )

    summary = texts.ORDER_SUMMARY.format(
        panel_name=panel.name,
        plan_type=plan_type,
        plan_name=plan.name,
        duration=plan.duration_days,
        traffic=(
            "نامحدود"
            if plan.traffic_gb <= 0
            else plan.traffic_gb
        ),
        amount=plan.price,
        currency=settings.CURRENCY_LABEL,
    )

    await state.set_state(
        BuyFlow.waiting_payment_method
    )

    await message.answer(
        summary
        + "\n\n"
        + f"📱 نام کانفیگ: {name}"
        + "\n\n"
        + texts.CHOOSE_PAYMENT,
        reply_markup=payment_methods_kb(
            plan.id
        ),
    )


# ==========================================================
# بازگشت از مرحله نام کانفیگ
# ==========================================================

@router.callback_query(
    BuyFlow.waiting_config_name,
    F.data == "config_name:default",
)
async def use_default_config_name(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    data = await state.get_data()

    plan_id = data.get("plan_id")

    if not plan_id:
        await state.clear()

        await callback.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )
        return

    plan = await get_plan(
        session,
        int(plan_id),
    )

    if plan is None or not plan.is_active:
        await state.clear()

        await callback.answer(
            "این پلن دیگر موجود نیست.",
            show_alert=True,
        )
        return

    config_name = "کانفیگ من"

    await state.update_data(
        config_name=config_name,
    )

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        await state.clear()

        await callback.answer(
            "پنل مربوط به این پلن پیدا نشد.",
            show_alert=True,
        )
        return

    plan_type = PLAN_TYPE_LABELS.get(
        plan.plan_type,
        plan.plan_type,
    )

    summary = texts.ORDER_SUMMARY.format(
        panel_name=panel.name,
        plan_type=plan_type,
        plan_name=plan.name,
        duration=plan.duration_days,
        traffic=(
            "نامحدود"
            if plan.traffic_gb <= 0
            else plan.traffic_gb
        ),
        amount=plan.price,
        currency=settings.CURRENCY_LABEL,
    )

    await state.set_state(
        BuyFlow.waiting_payment_method
    )

    await callback.message.edit_text(
        summary
        + "\n\n"
        + f"📱 نام کانفیگ: {config_name}"
        + "\n\n"
        + texts.CHOOSE_PAYMENT,
        reply_markup=payment_methods_kb(
            plan.id
        ),
    )

    await callback.answer()


# ==========================================================
# لغو خرید
# ==========================================================

@router.callback_query(
    BuyFlow.waiting_config_name,
    F.data == "buy_cancel",
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


# ==========================================================
# پرداخت زرین پال
# ==========================================================

@router.callback_query(
    BuyFlow.waiting_payment_method,
    F.data.startswith("pay:zarinpal:"),
)
async def pay_zarinpal(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = int(
        callback.data.split(":")[2]
    )

    data = await state.get_data()

    config_name = data.get(
        "config_name",
        "کانفیگ من",
    )

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is None or not plan.is_active:
        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )
        return

    # ------------------------------------------------------
    # پیدا کردن کاربر
    # ------------------------------------------------------

    from app.database.crud import get_or_create_user

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
    )

    # ------------------------------------------------------
    # ساخت سفارش
    # ------------------------------------------------------

    order = await create_order(
        session,
        user,
        plan,
        PaymentMethod.ZARINPAL,
        config_name=config_name,
    )

    # ------------------------------------------------------
    # درخواست پرداخت
    # ------------------------------------------------------

    try:

        authority, pay_link = (
            await zarinpal.request_payment(
                amount_toman=plan.price,
                description=(
                    f"خرید پلن {plan.name} "
                    f"- سفارش #{order.id}"
                ),
                order_id=order.id,
            )
        )

    except zarinpal.ZarinpalError as e:

        await callback.message.answer(
            "⚠️ خطا در اتصال به زرین‌پال:\n\n"
            f"{e}"
        )

        await callback.answer()
        return

    # ------------------------------------------------------
    # ذخیره Authority
    # ------------------------------------------------------

    order.zarinpal_authority = authority

    await session.commit()

    # ------------------------------------------------------
    # پاک کردن FSM
    # ------------------------------------------------------

    await state.clear()

    # ------------------------------------------------------
    # ارسال لینک پرداخت
    # ------------------------------------------------------

    from app.keyboards.payment_kb import (
        zarinpal_pay_kb,
    )

    await callback.message.edit_text(
        texts.ZARINPAL_LINK,
        reply_markup=zarinpal_pay_kb(
            pay_link
        ),
    )

    await callback.answer()


# ==========================================================
# پرداخت کارت به کارت
# ==========================================================

@router.callback_query(
    BuyFlow.waiting_payment_method,
    F.data.startswith("pay:card:"),
)
async def pay_card(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = int(
        callback.data.split(":")[2]
    )

    data = await state.get_data()

    config_name = data.get(
        "config_name",
        "کانفیگ من",
    )

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is None or not plan.is_active:
        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )
        return

    from app.database.crud import get_or_create_user

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
    )

    order = await create_order(
        session,
        user,
        plan,
        PaymentMethod.CARD,
        config_name=config_name,
    )

    await session.commit()

    await state.clear()

    card_text = (
        "💳 <b>پرداخت کارت به کارت</b>\n\n"
        f"📦 پلن: {plan.name}\n"
        f"📱 نام کانفیگ: {config_name}\n"
        f"💰 مبلغ: {plan.price:,} "
        f"{settings.CURRENCY_LABEL}\n\n"
        f"🏦 بانک: {settings.CARD_BANK_NAME}\n"
        f"👤 صاحب حساب: {settings.CARD_HOLDER_NAME}\n"
        f"💳 شماره کارت:\n"
        f"<code>{settings.CARD_NUMBER}</code>\n\n"
        "بعد از پرداخت، رسید خود را ارسال کنید."
    )

    await callback.message.edit_text(
        card_text,
        parse_mode="HTML",
    )

    await callback.answer()


# ==========================================================
# پرداخت کریپتو
# ==========================================================

@router.callback_query(
    BuyFlow.waiting_payment_method,
    F.data.startswith("pay:crypto:"),
)
async def pay_crypto(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    parts = callback.data.split(":")

    if len(parts) < 3:
        await callback.answer(
            "اطلاعات پرداخت نامعتبر است.",
            show_alert=True,
        )
        return

    plan_id = int(parts[2])

    data = await state.get_data()

    config_name = data.get(
        "config_name",
        "کانفیگ من",
    )

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is None or not plan.is_active:
        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )
        return

    await state.clear()

    await callback.message.edit_text(
        "🪙 پرداخت کریپتو\n\n"
        f"📦 پلن: {plan.name}\n"
        f"📱 نام کانفیگ: {config_name}\n"
        f"💰 مبلغ: {plan.price:,} "
        f"{settings.CURRENCY_LABEL}\n\n"
        "⚠️ بخش پرداخت کریپتو باید بر اساس ارز "
        "انتخاب‌شده ادامه پیدا کند."
    )

    await callback.answer()


# ==========================================================
# انتخاب روش پرداخت
# ==========================================================

@router.callback_query(
    F.data == "buy_back",
)
async def buy_back(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.clear()

    await callback.message.edit_text(
        "خرید لغو شد."
    )

    await callback.answer()