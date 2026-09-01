from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Order, VpnConfig
from app.services.sanaei_client import SanaeiApiError, SanaeiClient


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

    panel = settings.PANELS.get(plan.panel_key)
    if panel is None:
        raise SanaeiApiError(f"پنل «{plan.panel_key}» پیدا نشد.")

    email = (order.config_name or "").strip() or f"user-{user.telegram_id}-{order.id}"

    print(
        f"DEBUG CONFIG NAME | "
        f"order_id={order.id} | "
        f"order.config_name={order.config_name!r} | "
        f"email={email!r}"
    )

    client = SanaeiClient(panel)

    try:
        result = await client.add_client(
            email=email,
            traffic_gb=plan.traffic_gb,
            traffic_mb=plan.traffic_mb if plan.is_trial else None,
            duration_days=plan.duration_days,
            inbound_id=panel.inbound_id,
        )

        client_uuid = result["client_uuid"]
        sub_id = result["sub_id"]
        subscription_link = result["subscription_link"]
        subscription_links = result.get("subscription_links", [])
        individual_links = result.get("individual_links", [])

        expire_at = datetime.now(timezone.utc) + timedelta(days=plan.duration_days)

        vpn_config = VpnConfig(
            order_id=order.id,
            user_id=user.id,
            panel_key=panel.key,
            plan_type=plan.plan_type,
            plan_name=plan.name,
            config_name=email,
            inbound_id=panel.inbound_id,
            client_email=email,
            client_uuid=client_uuid,
            config_link=subscription_link,
            traffic_gb=plan.traffic_gb,
            expire_at=expire_at,
            subscription_link=subscription_link,
        )

        session.add(vpn_config)

        await session.commit()

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
            f"📦 <b>پلن:</b> {plan.name}\n"
            f"🌐 <b>سرور:</b> {panel.name}\n"
            f"📊 <b>حجم:</b> {traffic_text}\n"
            f"⏳ <b>مدت:</b> {plan.duration_days} روز\n"
            f"📱 <b>نام کانفیگ:</b> {email}\n\n"
            "🔗 <b>Subscription:</b>\n"
            f"<code>{subscription_link}</code>\n\n"
            f"📡 <b>تعداد کانفیگ‌های تکی:</b> {len(subscription_links)}\n\n"
            "از بخش «📂 کانفیگ‌های من» می‌توانید "
            "Subscription و کانفیگ‌های تکی را دریافت کنید."
        )

        await bot.send_message(
            user.telegram_id,
            text,
            parse_mode="HTML",
        )

    finally:
        await client.close()