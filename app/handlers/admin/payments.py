from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import get_order, list_pending_orders, mark_order_paid, mark_order_rejected
from app.database.models import OrderStatus
from app.keyboards.admin_kb import order_review_kb
from app.middlewares.admin_filter import IsAdmin
from app.services.delivery import provision_and_deliver
from app.services.sanaei_client import SanaeiApiError
from app.utils import texts

router = Router(name="admin_payments")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("pending"))
async def pending_orders(message: Message, session: AsyncSession) -> None:
    orders = await list_pending_orders(session)
    if not orders:
        await message.answer(texts.NO_PENDING_ORDERS)
        return
    for order in orders:
        text = (
            f"سفارش #{order.id} — {order.payment_method.value}\n"
            f"کاربر: {order.user.telegram_id}\n"
            f"پلن: {order.plan.name} — {order.amount:,} {settings.CURRENCY_LABEL}\n"
        )
        if order.crypto_tx_id:
            text += f"TxID: `{order.crypto_tx_id}`\n"
        await message.answer(text, reply_markup=order_review_kb(order.id), parse_mode="Markdown")


@router.callback_query(F.data.startswith("admin_approve:"))
async def approve_order(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order(session, order_id)
    if order is None or order.status != OrderStatus.PENDING:
        await callback.answer("این سفارش دیگر در انتظار نیست.", show_alert=True)
        return

    await mark_order_paid(session, order, admin_id=callback.from_user.id)

    try:
        await provision_and_deliver(bot, session, order)
    except SanaeiApiError as e:
        await callback.message.answer(f"⚠️ پرداخت تایید شد ولی ساخت کانفیگ روی پنل خطا داد: {e}")
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ سفارش #{order.id} تایید و کانفیگ برای کاربر ارسال شد.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject:"))
async def reject_order(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order(session, order_id)
    if order is None or order.status != OrderStatus.PENDING:
        await callback.answer("این سفارش دیگر در انتظار نیست.", show_alert=True)
        return

    await mark_order_rejected(session, order, admin_id=callback.from_user.id)

    await bot.send_message(
        order.user.telegram_id,
        texts.ORDER_REJECTED_USER.format(order_id=order.id, support=settings.SUPPORT_USERNAME),
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ سفارش #{order.id} رد شد.")
    await callback.answer()
