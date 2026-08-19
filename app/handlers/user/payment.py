from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import create_order, get_or_create_user, get_order, get_plan
from app.database.models import PaymentMethod
from app.keyboards.admin_kb import order_review_kb
from app.keyboards.user_kb import crypto_coins_kb, zarinpal_pay_kb
from app.services import zarinpal
from app.states.user_states import BuyFlow
from app.utils import texts

router = Router(name="payment")


async def _get_user_and_plan(session: AsyncSession, callback: CallbackQuery, plan_id: int):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    plan = await get_plan(session, plan_id)
    return user, plan


# ---------------------------------------------------------------- زرین‌پال
@router.callback_query(F.data.startswith("pay:zarinpal:"))
async def pay_zarinpal(callback: CallbackQuery, session: AsyncSession) -> None:
    plan_id = int(callback.data.split(":")[2])
    user, plan = await _get_user_and_plan(session, callback, plan_id)
    if plan is None:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    order = await create_order(session, user, plan, PaymentMethod.ZARINPAL)

    try:
        authority, pay_link = await zarinpal.request_payment(
            amount_toman=plan.price,
            description=f"خرید پلن {plan.name} - سفارش #{order.id}",
            order_id=order.id,
        )
    except zarinpal.ZarinpalError as e:
        await callback.message.answer(f"⚠️ خطا در اتصال به زرین‌پال: {e}")
        await callback.answer()
        return

    order.zarinpal_authority = authority
    await session.commit()

    await callback.message.answer(texts.ZARINPAL_LINK, reply_markup=zarinpal_pay_kb(pay_link))
    await callback.answer()


# ------------------------------------------------------------- کارت به کارت
@router.callback_query(F.data.startswith("pay:card:"))
async def pay_card(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    plan_id = int(callback.data.split(":")[2])
    user, plan = await _get_user_and_plan(session, callback, plan_id)
    if plan is None:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    order = await create_order(session, user, plan, PaymentMethod.CARD)
    await state.update_data(order_id=order.id)
    await state.set_state(BuyFlow.waiting_card_receipt)

    await callback.message.answer(
        texts.CARD_INFO.format(
            amount=plan.price,
            currency=settings.CURRENCY_LABEL,
            card_number=settings.CARD_NUMBER,
            holder=settings.CARD_HOLDER_NAME,
            bank=settings.CARD_BANK_NAME,
        ),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(BuyFlow.waiting_card_receipt, F.photo)
async def receive_card_receipt(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order = await get_order(session, data["order_id"])
    if order is None:
        await message.answer("سفارش پیدا نشد، لطفاً دوباره از منو شروع کن.")
        await state.clear()
        return

    order.receipt_file_id = message.photo[-1].file_id
    await session.commit()
    await state.clear()

    await message.answer(texts.CARD_RECEIPT_RECEIVED)

    caption = texts.ADMIN_NEW_CARD_ORDER.format(
        order_id=order.id,
        user_mention=message.from_user.full_name,
        telegram_id=message.from_user.id,
        plan_name=order.plan.name,
        amount=order.amount,
        currency=settings.CURRENCY_LABEL,
    )
    for admin_id in settings.ADMIN_IDS:
        await bot.send_photo(
            chat_id=admin_id,
            photo=order.receipt_file_id,
            caption=caption,
            reply_markup=order_review_kb(order.id),
        )


# ------------------------------------------------------------------ رمزارز
@router.callback_query(F.data.startswith("pay:crypto:"))
async def pay_crypto(callback: CallbackQuery, session: AsyncSession) -> None:
    plan_id = int(callback.data.split(":")[2])
    await callback.message.answer(texts.CRYPTO_CHOOSE_COIN, reply_markup=crypto_coins_kb(plan_id))
    await callback.answer()


@router.callback_query(F.data.startswith("crypto_coin:"))
async def choose_crypto_coin(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    _, coin, plan_id = callback.data.split(":")
    plan_id = int(plan_id)
    user, plan = await _get_user_and_plan(session, callback, plan_id)
    if plan is None:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    order = await create_order(session, user, plan, PaymentMethod.CRYPTO)
    order.crypto_coin = coin
    await session.commit()

    await state.update_data(order_id=order.id)
    await state.set_state(BuyFlow.waiting_crypto_txid)

    address = getattr(settings.CRYPTO_WALLETS, coin)
    await callback.message.answer(
        texts.CRYPTO_INFO.format(
            amount=plan.price,
            currency=settings.CURRENCY_LABEL,
            coin=coin.upper(),
            address=address,
        ),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(BuyFlow.waiting_crypto_txid, F.text)
async def receive_crypto_txid(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order = await get_order(session, data["order_id"])
    if order is None:
        await message.answer("سفارش پیدا نشد، لطفاً دوباره از منو شروع کن.")
        await state.clear()
        return

    order.crypto_tx_id = message.text.strip()
    await session.commit()
    await state.clear()

    await message.answer(texts.CRYPTO_TX_RECEIVED)

    text = texts.ADMIN_NEW_CRYPTO_ORDER.format(
        order_id=order.id,
        user_mention=message.from_user.full_name,
        telegram_id=message.from_user.id,
        plan_name=order.plan.name,
        amount=order.amount,
        currency=settings.CURRENCY_LABEL,
        coin=order.crypto_coin.upper(),
        tx_id=order.crypto_tx_id,
    )
    for admin_id in settings.ADMIN_IDS:
        await bot.send_message(admin_id, text, reply_markup=order_review_kb(order.id), parse_mode="Markdown")
