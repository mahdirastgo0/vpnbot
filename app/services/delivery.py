from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from aiogram import Bot
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Order, VpnConfig
from app.services.panel_manager import get_client
from app.services.sanaei_client import SanaeiApiError

logger = logging.getLogger(__name__)


def _client_email(config_name: str, order_id: int) -> str:
    # email در پنل باید یکتا باشد؛ اگر دو کاربر یک اسم انتخاب کنند،
    # بدون شماره سفارش پنل خطای Duplicate email می‌دهد.
    base = config_name.strip().replace(" ", "_")[:100]
    return f"{base}-{order_id}"


async def provision_and_deliver(
    bot: Bot,
    session: AsyncSession,
    order: Order,
) -> None:

    plan = order.plan
    user = order.user

    if plan is None:
        raise SanaeiApiError("پلن سفارش پیدا نشد.")

    if user is None:
        raise SanaeiApiError("کاربر سفارش پیدا نشد.")

    # فقط اگر رابطه از قبل لود شده باشد چک می‌کنیم (lazy load در async خطا می‌دهد)
    if (
        "vpn_config" not in inspect(order).unloaded
        and order.vpn_config is not None
    ):
        raise SanaeiApiError(
            f"برای سفارش #{order.id} قبلاً کانفیگ ساخته شده است."
        )

    panel = settings.PANELS.get(plan.panel_key)

    if panel is None:
        raise SanaeiApiError(
            f"پنل «{plan.panel_key}» پیدا نشد."
        )

    # ============================================================
    # نام کانفیگ (نمایشی) و email یکتا در پنل
    # ============================================================

    config_name = (order.config_name or "").strip() or f"user-{user.telegram_id}"
    email = _client_email(config_name, order.id)

    logger.info(
        "Provisioning order_id=%s config_name=%r email=%r",
        order.id, config_name, email,
    )

    client = get_client(panel.key)

    # ========================================================
    # ساخت Client در پنل
    # ========================================================

    result = await client.add_client(
        email=email,
        traffic_gb=plan.traffic_gb,
        traffic_mb=(
            plan.traffic_mb
            if plan.is_trial
            else None
        ),
        duration_days=plan.duration_days,
        inbound_id=panel.inbound_id,
    )

    client_uuid = result["client_uuid"]
    subscription_link = result.get("subscription_link")
    individual_links = result.get("individual_links", [])

    # ========================================================
    # اضافه کردن نام انتخابی کاربر به لینک تکی
    # (نام قبلی بعد از # حذف و نام جدید جایگزین می‌شود)
    # ========================================================

    fragment = quote(config_name, safe="")

    individual_links = [
        f"{link.strip().split('#', 1)[0]}#{fragment}"
        for link in individual_links
        if isinstance(link, str) and link.strip()
    ]

    # ========================================================
    # ذخیره کانفیگ در دیتابیس
    #
    # config_link یک Text است، بنابراین لینک‌ها را
    # به صورت JSON ذخیره می‌کنیم.
    # ========================================================

    expire_at = (
        datetime.now(timezone.utc)
        + timedelta(days=plan.duration_days)
    )

    vpn_config = VpnConfig(
        order_id=order.id,
        user_id=user.id,
        panel_key=panel.key,
        plan_type=plan.plan_type,
        plan_name=plan.name,
        config_name=config_name,
        inbound_id=panel.inbound_id,
        client_email=email,
        client_uuid=client_uuid,
        config_link=json.dumps(individual_links, ensure_ascii=False),
        traffic_gb=plan.traffic_gb,
        expire_at=expire_at,
        subscription_link=subscription_link,
    )

    session.add(vpn_config)

    await session.commit()

    # ========================================================
    # پیام تحویل سرویس
    #
    # کانفیگ ساخته و ذخیره شده؛ اگر ارسال پیام شکست بخورد
    # (مثلاً کاربر ربات را بلاک کرده) نباید کل عملیات خطا بدهد،
    # وگرنه سفارش در انتظار می‌ماند و تایید دوباره کانفیگ تکراری می‌سازد.
    # ========================================================

    if plan.is_trial and plan.traffic_mb:
        traffic_text = f"{plan.traffic_mb} MB"
    elif plan.traffic_gb <= 0:
        traffic_text = "نامحدود"
    else:
        traffic_text = f"{plan.traffic_gb} GB"

    title = (
        "🎁 <b>سرویس تست رایگان شما آماده شد!</b>"
        if plan.is_trial
        else "🎉 <b>خرید شما با موفقیت انجام شد!</b>"
    )

    text = (
        f"{title}\n\n"
        f"📦 <b>پلن:</b> {escape(plan.name)}\n"
        f"🌐 <b>سرور:</b> {escape(panel.name)}\n"
        f"📊 <b>حجم:</b> {traffic_text}\n"
        f"⏳ <b>مدت:</b> {plan.duration_days} روز\n"
        f"📱 <b>نام کانفیگ:</b> {escape(config_name)}\n\n"
        f"📡 <b>تعداد کانفیگ‌های تکی:</b> "
        f"{len(individual_links)}\n\n"
        "🔗 <b>Subscription:</b>\n"
        f"<code>{escape(subscription_link or 'ندارد')}</code>\n\n"
        "از بخش «📂 کانفیگ‌های من» می‌توانید "
        "کانفیگ تکی یا Subscription را دریافت کنید."
    )

    try:
        await bot.send_message(
            user.telegram_id,
            text,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Config for order_id=%s created but sending to user %s failed",
            order.id, user.telegram_id,
        )
