from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
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

# ==========================================================
# فقط ادمین
# ==========================================================

router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ==========================================================
# سفارش‌های در انتظار
# ==========================================================

@router.message(Command("pending"))
async def pending_orders(
    message: Message,
    session: AsyncSession,
) -> None:

    orders = await list_pending_orders(session)

    if not orders:
        await message.answer(
            texts.NO_PENDING_ORDERS
        )
        return

    for order in orders:

        text = (
            f"🧾 سفارش #{order.id}\n"
            f"💳 پرداخت: {order.payment_method.value}\n"
            f"👤 کاربر: {order.user.telegram_id}\n"
            f"📦 پلن: {order.plan.name}\n"
            f"💰 مبلغ: {order.amount:,} "
            f"{settings.CURRENCY_LABEL}\n"
            f"📱 نام کانفیگ: "
            f"{order.config_name or 'کانفیگ من'}\n"
        )

        if order.crypto_coin:
            text += (
                f"🪙 ارز: "
                f"{order.crypto_coin.upper()}\n"
            )

        if order.crypto_tx_id:
            text += (
                f"🔗 TxID: "
                f"`{order.crypto_tx_id}`\n"
            )

        await message.answer(
            text,
            reply_markup=order_review_kb(order.id),
            parse_mode="Markdown",
        )


# ==========================================================
# تایید سفارش
# ==========================================================

@router.callback_query(
    F.data.startswith("admin_approve:")
)
async def approve_order(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:

    order_id = int(
        callback.data.split(":")[1]
    )

    order = await get_order(
        session,
        order_id,
    )

    # ------------------------------------------------------
    # سفارش وجود ندارد
    # ------------------------------------------------------

    if order is None:

        await callback.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # سفارش قبلاً بررسی شده
    # ------------------------------------------------------

    if order.status != OrderStatus.PENDING:

        await callback.answer(
            "این سفارش دیگر در انتظار نیست.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # ساخت کانفیگ
    # ------------------------------------------------------

    try:

        await provision_and_deliver(
            bot,
            session,
            order,
        )

    except SanaeiApiError as e:

        await callback.message.answer(
            f"⚠️ پرداخت هنوز نهایی نشد.\n\n"
            f"❌ خطا در ساخت کانفیگ روی پنل:\n"
            f"{e}\n\n"
            f"سفارش #{order.id} همچنان "
            f"در وضعیت انتظار است."
        )

        await callback.answer(
            "ساخت کانفیگ ناموفق بود.",
            show_alert=True,
        )

        return

    except Exception as e:

        await callback.message.answer(
            f"⚠️ خطای غیرمنتظره در ساخت "
            f"کانفیگ سفارش #{order.id}\n\n"
            f"{e}\n\n"
            f"سفارش همچنان در انتظار است."
        )

        await callback.answer(
            "خطا در ساخت کانفیگ.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # کانفیگ با موفقیت ساخته شده
    # ------------------------------------------------------

    await mark_order_paid(
        session,
        order,
        admin_id=callback.from_user.id,
    )

    # ------------------------------------------------------
    # حذف دکمه‌های سفارش
    # ------------------------------------------------------

    try:

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

    except Exception:
        pass

    # ------------------------------------------------------
    # پیام به ادمین
    # ------------------------------------------------------

    await callback.message.answer(
        f"✅ سفارش #{order.id} تایید شد.\n\n"
        f"🔐 کانفیگ با موفقیت ساخته شد "
        f"و برای کاربر ارسال شد."
    )

    await callback.answer(
        "سفارش با موفقیت تایید شد."
    )


# ==========================================================
# رد سفارش
# ==========================================================

@router.callback_query(
    F.data.startswith("admin_reject:")
)
async def reject_order(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:

    order_id = int(
        callback.data.split(":")[1]
    )

    order = await get_order(
        session,
        order_id,
    )

    # ------------------------------------------------------
    # سفارش وجود ندارد
    # ------------------------------------------------------

    if order is None:

        await callback.answer(
            "سفارش پیدا نشد.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # سفارش قبلاً بررسی شده
    # ------------------------------------------------------

    if order.status != OrderStatus.PENDING:

        await callback.answer(
            "این سفارش دیگر در انتظار نیست.",
            show_alert=True,
        )

        return

    # ------------------------------------------------------
    # رد سفارش
    # ------------------------------------------------------

    await mark_order_rejected(
        session,
        order,
        admin_id=callback.from_user.id,
    )

    # ------------------------------------------------------
    # اطلاع به کاربر
    # ------------------------------------------------------

    await bot.send_message(
        order.user.telegram_id,
        texts.ORDER_REJECTED_USER.format(
            order_id=order.id,
            support=settings.SUPPORT_USERNAME,
        ),
    )

    # ------------------------------------------------------
    # حذف دکمه‌ها
    # ------------------------------------------------------

    try:

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

    except Exception:
        pass

    # ------------------------------------------------------
    # پیام به ادمین
    # ------------------------------------------------------

    await callback.message.answer(
        f"❌ سفارش #{order.id} رد شد."
    )

    await callback.answer(
        "سفارش رد شد."
    )