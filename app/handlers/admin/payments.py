from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import (
    get_order,
    list_pending_orders,
    mark_order_paid,
    mark_order_rejected,
)
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
async def pending_orders(
    message: Message,
    session: AsyncSession,
) -> None:

    orders = await list_pending_orders(session)

    if not orders:
        await message.answer(texts.NO_PENDING_ORDERS)
        return

    for order in orders:
        text = (
            f"🧾 سفارش #{order.id}\n"
            f"💳 پرداخت: {order.payment_method.value}\n"
            f"👤 کاربر: {order.user.telegram_id}\n"
            f"📦 پلن: {order.plan.name}\n"
            f"💰 مبلغ: {order.amount:,} {settings.CURRENCY_LABEL}\n"
            f"📱 نام کانفیگ: {order.config_name or 'کانفیگ من'}\n"
        )

        if order.crypto_coin:
            text += f"🪙 ارز: {order.crypto_coin.upper()}\n"

        if order.crypto_tx_id:
            text += f"🔗 TxID: `{order.crypto_tx_id}`\n"

        await message.answer(
            text,
            reply_markup=order_review_kb(order.id),
            parse_mode="Markdown",
        )

@router.callback_query(F.data.startswith("admin_approve:"))
async def approve_order(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:

    order_id = int(callback.data.split(":")[1])

    order = await get_order(
        session,
        order_id,
    )

    # --------------------------------------------------
    # بررسی سفارش
    # --------------------------------------------------
    if order is None:
        await callback.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )
        return

    if order.status != OrderStatus.PENDING:
        await callback.answer(
            "این سفارش دیگر در انتظار نیست.",
            show_alert=True,
        )
        return

    # --------------------------------------------------
    # اول کانفیگ را بساز
    #
    # اگر ساخت کانفیگ شکست بخورد:
    # سفارش همچنان PENDING باقی می‌ماند
    # --------------------------------------------------
    try:
        await provision_and_deliver(
            bot,
            session,
            order,
        )

    except SanaeiApiError as e:
        await callback.message.answer(
            f"⚠️ پرداخت هنوز نهایی نشد.\n"
            f"ساخت کانفیگ روی پنل خطا داد:\n\n"
            f"{e}\n\n"
            f"سفارش #{order.id} همچنان در انتظار است "
            f"و می‌توانی دوباره تلاش کنی."
        )

        await callback.answer(
            "ساخت کانفیگ ناموفق بود.",
            show_alert=True,
        )
        return

    except Exception as e:
        await callback.message.answer(
            f"⚠️ ساخت کانفیگ برای سفارش #{order.id} "
            f"با خطای غیرمنتظره مواجه شد.\n\n"
            f"{e}\n\n"
            f"سفارش همچنان در وضعیت انتظار باقی ماند."
        )

        await callback.answer(
            "خطا در ساخت کانفیگ.",
            show_alert=True,
        )
        return

    # --------------------------------------------------
    # کانفیگ با موفقیت ساخته شده
    # حالا سفارش را PAID می‌کنیم
    # --------------------------------------------------
    await mark_order_paid(
        session,
        order,
        admin_id=callback.from_user.id,
    )

    # حذف دکمه‌های تأیید/رد
    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.message.answer(
        f"✅ سفارش #{order.id} تایید شد.\n"
        f"🔐 کانفیگ با موفقیت ساخته و برای کاربر ارسال شد."
    )

    await callback.answer(
        "سفارش با موفقیت تایید شد."
    )


@router.callback_query(F.data.startswith("admin_reject:"))
async def reject_order(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:

    order_id = int(callback.data.split(":")[1])

    order = await get_order(
        session,
        order_id,
    )

    if order is None:
        await callback.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )
        return

    if order.status != OrderStatus.PENDING:
        await callback.answer(
            "این سفارش دیگر در انتظار نیست.",
            show_alert=True,
        )
        return

    await mark_order_rejected(
        session,
        order,
        admin_id=callback.from_user.id,
    )

    await bot.send_message(
        order.user.telegram_id,
        texts.ORDER_REJECTED_USER.format(
            order_id=order.id,
            support=settings.SUPPORT_USERNAME,
        ),
    )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.message.answer(
        f"❌ سفارش #{order.id} رد شد."
    )

    await callback.answer(
        "سفارش رد شد."
    )

@router.callback_query(F.data.startswith("pay:zarinpal:"))
async def pay_zarinpal(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    plan_id = int(callback.data.split(":")[2])

    data = await state.get_data()
    config_name = data.get("config_name")

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
        config_name=config_name,
    )

    await state.clear()

    try:
        authority, pay_link = await zarinpal.request_payment(
            amount_toman=plan.price,
            description=f"خرید پلن {plan.name} - سفارش #{order.id}",
            order_id=order.id,
        )
    except zarinpal.ZarinpalError as e:
        await callback.message.answer(
            f"⚠️ خطا در اتصال به زرین‌پال: {e}"
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