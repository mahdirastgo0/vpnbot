from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
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

# سفارش‌هایی که در حال ساخت کانفیگ هستند
_approving_orders: set[int] = set()


async def _safe_answer(
    callback: CallbackQuery,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    # اگر callback منقضی شده باشد، تلگرام خطا می‌دهد؛ نادیده می‌گیریم.
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
        pass


# ==========================================================
# سفارش‌های در انتظار
# ==========================================================

async def _send_pending_orders(
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
            f"📦 پلن: {escape(order.plan.name)}\n"
            f"💰 مبلغ: {order.amount:,} "
            f"{settings.CURRENCY_LABEL}\n"
            f"📱 نام کانفیگ: "
            f"{escape(order.config_name or 'کانفیگ من')}\n"
        )

        if order.crypto_coin:
            text += (
                f"🪙 ارز: "
                f"{escape(order.crypto_coin.upper())}\n"
            )

        if order.crypto_tx_id:
            text += (
                f"🔗 TxID: "
                f"<code>{escape(order.crypto_tx_id)}</code>\n"
            )

        if order.receipt_file_id:
            await message.answer_photo(
                order.receipt_file_id,
                caption=text,
                reply_markup=order_review_kb(order.id),
            )
        else:
            await message.answer(
                text,
                reply_markup=order_review_kb(order.id),
            )


@router.message(Command("pending"))
async def pending_orders(
    message: Message,
    session: AsyncSession,
) -> None:
    await _send_pending_orders(message, session)


@router.callback_query(F.data == "admin_pending_orders")
async def pending_orders_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await _send_pending_orders(callback.message, session)


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
    # جلوگیری از تایید هم‌زمان (دوبار کلیک)
    # ------------------------------------------------------

    if order.id in _approving_orders:

        await _safe_answer(
            callback,
            "این سفارش در حال پردازش است...",
        )

        return

    # ------------------------------------------------------
    # پاسخ فوری به callback
    #
    # تلگرام فقط حدود ۱۵ ثانیه برای پاسخ به callback صبر می‌کند
    # و ساخت کانفیگ روی پنل ممکن است طولانی‌تر شود.
    # ------------------------------------------------------

    await _safe_answer(
        callback,
        "⏳ در حال ساخت کانفیگ...",
    )

    # ------------------------------------------------------
    # ساخت کانفیگ
    # ------------------------------------------------------

    _approving_orders.add(order.id)

    try:

        # اگر کانفیگ قبلاً ساخته شده (مثلاً تلاش قبلی بعد از ساخت قطع شده)
        # دوباره نمی‌سازیم و فقط سفارش را نهایی می‌کنیم.
        if order.vpn_config is None:
            await provision_and_deliver(
                bot,
                session,
                order,
            )

    except SanaeiApiError as e:

        await callback.message.answer(
            f"⚠️ پرداخت هنوز نهایی نشد.\n\n"
            f"❌ خطا در ساخت کانفیگ روی پنل:\n"
            f"{escape(str(e))}\n\n"
            f"سفارش #{order.id} همچنان "
            f"در وضعیت انتظار است."
        )

        return

    except Exception as e:

        await callback.message.answer(
            f"⚠️ خطای غیرمنتظره در ساخت "
            f"کانفیگ سفارش #{order.id}\n\n"
            f"{escape(str(e))}\n\n"
            f"سفارش همچنان در انتظار است."
        )

        return

    finally:
        _approving_orders.discard(order.id)

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

    try:
        await bot.send_message(
            order.user.telegram_id,
            texts.ORDER_REJECTED_USER.format(
                order_id=order.id,
                support=settings.SUPPORT_USERNAME,
            ),
        )
    except Exception:
        # کاربر ممکن است ربات را بلاک کرده باشد
        pass

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