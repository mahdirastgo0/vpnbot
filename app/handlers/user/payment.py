from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import (
    create_order,
    get_or_create_user,
    get_order,
    get_plan,
)
from app.database.models import PaymentMethod
from app.keyboards.admin_kb import order_review_kb
from app.keyboards.payment_kb import card_payment_kb
from app.keyboards.user_kb import MENU_BUTTONS, crypto_coins_kb, zarinpal_pay_kb
from app.services import zarinpal
from app.states.user_states import BuyFlow
from app.utils import texts


logger = logging.getLogger(__name__)

router = Router(name="payment")


# ==========================================================
# دریافت کاربر و پلن
# ==========================================================

async def _get_user_and_plan(
    session: AsyncSession,
    callback: CallbackQuery,
    plan_id: int,
):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    plan = await get_plan(
        session,
        plan_id,
    )

    if plan is not None and (not plan.is_active or plan.is_trial):
        plan = None

    return user, plan


def _parse_plan_id(data: str, index: int = 2) -> int | None:
    try:
        return int(data.split(":")[index])
    except (ValueError, IndexError):
        return None


async def _config_name(state: FSMContext) -> str | None:
    # نامی که کاربر در مرحله قبل انتخاب کرده
    data = await state.get_data()
    return data.get("config_name")


async def _notify_admins(bot: Bot, **kwargs) -> None:
    # خطای ارسال به یک ادمین نباید ارسال به بقیه را متوقف کند
    for admin_id in settings.ADMIN_IDS:
        try:
            if "photo" in kwargs:
                await bot.send_photo(chat_id=admin_id, **kwargs)
            else:
                await bot.send_message(chat_id=admin_id, **kwargs)
        except Exception:
            logger.exception("Failed to notify admin %s", admin_id)


# ==========================================================
# زرین‌پال
# ==========================================================

@router.callback_query(
    F.data.startswith("pay:zarinpal:")
)
async def pay_zarinpal(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = _parse_plan_id(callback.data)

    if plan_id is None:
        await callback.answer("پلن نامعتبر است.", show_alert=True)
        return

    user, plan = await _get_user_and_plan(
        session,
        callback,
        plan_id,
    )

    if plan is None:
        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )
        return

    order = await create_order(
        session,
        user,
        plan,
        PaymentMethod.ZARINPAL,
        config_name=await _config_name(state),
    )

    await state.clear()

    try:

        authority, pay_link = await zarinpal.request_payment(
            amount_toman=plan.price,
            description=(
                f"خرید پلن {plan.name} "
                f"- سفارش #{order.id}"
            ),
            order_id=order.id,
        )

    except zarinpal.ZarinpalError as e:

        await callback.message.answer(
            f"⚠️ خطا در اتصال به زرین‌پال:\n{escape(str(e))}"
        )

        await callback.answer()
        return

    order.zarinpal_authority = authority

    await session.commit()

    await callback.message.answer(
        texts.ZARINPAL_LINK,
        reply_markup=zarinpal_pay_kb(pay_link),
    )

    await callback.answer()


# ==========================================================
# کارت به کارت
# ==========================================================

@router.callback_query(
    F.data.startswith("pay:card:")
)
async def pay_card(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = _parse_plan_id(callback.data)

    if plan_id is None:
        await callback.answer("پلن نامعتبر است.", show_alert=True)
        return

    user, plan = await _get_user_and_plan(
        session,
        callback,
        plan_id,
    )

    if plan is None:
        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )
        return

    order = await create_order(
        session,
        user,
        plan,
        PaymentMethod.CARD,
        config_name=await _config_name(state),
    )

    await state.update_data(
        order_id=order.id
    )

    await state.set_state(
        BuyFlow.waiting_card_receipt
    )

    card_number = (
        settings.CARD_NUMBER
        .replace("||", "")
        .replace("`", "")
        .strip()
    )

    await callback.message.answer(
        texts.CARD_INFO.format(
            amount=plan.price,
            currency=settings.CURRENCY_LABEL,
            card_number=escape(card_number),
            holder=escape(settings.CARD_HOLDER_NAME),
            bank=escape(settings.CARD_BANK_NAME),
        ),
        reply_markup=card_payment_kb(card_number),
    )

    await callback.answer()


# ==========================================================
# دریافت رسید کارت به کارت
# ==========================================================

@router.message(
    BuyFlow.waiting_card_receipt,
    F.photo,
)
async def receive_card_receipt(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:

    data = await state.get_data()

    order_id = data.get("order_id")
    order = await get_order(session, int(order_id)) if order_id else None

    if order is None:

        await message.answer(
            "سفارش پیدا نشد، لطفاً دوباره از منو شروع کن."
        )

        await state.clear()
        return

    # ------------------------------------------------------
    # ذخیره رسید
    # ------------------------------------------------------

    order.receipt_file_id = (
        message.photo[-1].file_id
    )

    await session.commit()

    await state.clear()

    # ------------------------------------------------------
    # اطلاع به کاربر
    # ------------------------------------------------------

    await message.answer(
        texts.CARD_RECEIPT_RECEIVED
    )

    # ------------------------------------------------------
    # ارسال رسید برای ادمین‌ها
    # ------------------------------------------------------

    caption = texts.ADMIN_NEW_CARD_ORDER.format(
        order_id=order.id,
        user_mention=escape(message.from_user.full_name),
        telegram_id=message.from_user.id,
        plan_name=escape(order.plan.name),
        amount=order.amount,
        currency=settings.CURRENCY_LABEL,
    )

    await _notify_admins(
        bot,
        photo=order.receipt_file_id,
        caption=caption,
        reply_markup=order_review_kb(order.id),
    )


@router.message(
    BuyFlow.waiting_card_receipt,
    ~F.text.in_(MENU_BUTTONS),
)
async def receive_card_receipt_invalid(
    message: Message,
) -> None:

    await message.answer(
        "📸 لطفاً تصویر رسید پرداخت را به صورت عکس ارسال کن."
    )


# ==========================================================
# رمزارز
# ==========================================================

@router.callback_query(
    F.data.startswith("pay:crypto:")
)
async def pay_crypto(
    callback: CallbackQuery,
) -> None:

    plan_id = _parse_plan_id(callback.data)

    if plan_id is None:
        await callback.answer("پلن نامعتبر است.", show_alert=True)
        return

    await callback.message.answer(
        texts.CRYPTO_CHOOSE_COIN,
        reply_markup=crypto_coins_kb(
            plan_id
        ),
    )

    await callback.answer()


# ==========================================================
# انتخاب ارز دیجیتال
# ==========================================================

@router.callback_query(
    F.data.startswith("crypto_coin:")
)
async def choose_crypto_coin(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    try:
        _, coin, raw_plan_id = callback.data.split(":")
        plan_id = int(raw_plan_id)
    except ValueError:
        await callback.answer("اطلاعات نامعتبر است.", show_alert=True)
        return

    # آدرس کیف پول
    address = settings.CRYPTO_WALLETS.active_wallets().get(coin)

    if not address:
        await callback.answer(
            "این ارز در حال حاضر پشتیبانی نمی‌شود.",
            show_alert=True,
        )
        return

    user, plan = await _get_user_and_plan(
        session,
        callback,
        plan_id,
    )

    if plan is None:

        await callback.answer(
            "پلن یافت نشد.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # ساخت سفارش
    # ------------------------------------------------------

    order = await create_order(
        session,
        user,
        plan,
        PaymentMethod.CRYPTO,
        config_name=await _config_name(state),
    )

    order.crypto_coin = coin

    await session.commit()

    await state.update_data(
        order_id=order.id
    )

    await state.set_state(
        BuyFlow.waiting_crypto_txid
    )

    # ------------------------------------------------------
    # نمایش اطلاعات پرداخت
    # ------------------------------------------------------

    await callback.message.answer(
        texts.CRYPTO_INFO.format(
            amount=plan.price,
            currency=settings.CURRENCY_LABEL,
            coin=coin.upper(),
            address=escape(address),
        ),
    )

    await callback.answer()


# ==========================================================
# دریافت TxID رمزارز
# ==========================================================

@router.message(
    BuyFlow.waiting_crypto_txid,
    F.text,
    ~F.text.in_(MENU_BUTTONS),
)
async def receive_crypto_txid(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:

    tx_id = message.text.strip()

    if not tx_id or len(tx_id) > 128:
        await message.answer(
            "❌ هش تراکنش نامعتبر است. لطفاً TxID صحیح را ارسال کن."
        )
        return

    data = await state.get_data()

    order_id = data.get("order_id")
    order = await get_order(session, int(order_id)) if order_id else None

    if order is None:

        await message.answer(
            "سفارش پیدا نشد، لطفاً دوباره از منو شروع کن."
        )

        await state.clear()
        return

    # ------------------------------------------------------
    # ذخیره TxID
    # ------------------------------------------------------

    order.crypto_tx_id = tx_id

    await session.commit()

    await state.clear()

    # ------------------------------------------------------
    # اطلاع به کاربر
    # ------------------------------------------------------

    await message.answer(
        texts.CRYPTO_TX_RECEIVED
    )

    # ------------------------------------------------------
    # پیام ادمین
    # ------------------------------------------------------

    text = texts.ADMIN_NEW_CRYPTO_ORDER.format(
        order_id=order.id,
        user_mention=escape(message.from_user.full_name),
        telegram_id=message.from_user.id,
        plan_name=escape(order.plan.name),
        amount=order.amount,
        currency=settings.CURRENCY_LABEL,
        coin=escape(order.crypto_coin.upper()),
        tx_id=escape(order.crypto_tx_id),
    )

    await _notify_admins(
        bot,
        text=text,
        reply_markup=order_review_kb(order.id),
    )
