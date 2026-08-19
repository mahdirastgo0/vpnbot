from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Order, VpnConfig
from app.services.sanaei_client import (
    SanaeiApiError,
    SanaeiClient,
)


async def provision_and_deliver(
    bot: Bot,
    session: AsyncSession,
    order: Order,
) -> None:

    plan = order.plan
    user = order.user

    if plan is None:
        raise SanaeiApiError(
            "پلن سفارش پیدا نشد."
        )

    if user is None:
        raise SanaeiApiError(
            "کاربر سفارش پیدا نشد."
        )

    # ==========================================================
    # PANEL
    # ==========================================================

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        raise SanaeiApiError(
            f"پنل «{plan.panel_key}» پیدا نشد."
        )

    # ==========================================================
    # CONFIG NAME
    # ==========================================================

    email = (
        (order.config_name or "").strip()
        or f"user-{user.telegram_id}-{order.id}"
    )

    # ==========================================================
    # CREATE CLIENT
    # ==========================================================

    client = SanaeiClient(panel)

    try:

        result = await client.add_client(
            email=email,
            traffic_gb=plan.traffic_gb,
            duration_days=plan.duration_days,
            inbound_id=panel.inbound_id,
        )

        client_uuid = result["client_uuid"]
        sub_id = result["sub_id"]

        subscription_link = client.build_subscription_url(sub_id)

        individual_links = result.get("individual_links", [])

        subscription_links = result.get(
            "subscription_links",
            [],
        )

        # ======================================================
        # EXPIRY
        # ======================================================

        expire_at = (
            datetime.now(timezone.utc)
            + timedelta(
                days=plan.duration_days
            )
        )

        # ======================================================
        # VPN CONFIG
        # ======================================================

        vpn_config = order.vpn_config

        if vpn_config is None:

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

        else:

            vpn_config.panel_key = panel.key
            vpn_config.plan_type = plan.plan_type
            vpn_config.plan_name = plan.name
            vpn_config.config_name = email
            vpn_config.inbound_id = panel.inbound_id
            vpn_config.client_email = email
            vpn_config.client_uuid = client_uuid
            vpn_config.config_link = subscription_link
            vpn_config.traffic_gb = plan.traffic_gb
            vpn_config.expire_at = expire_at
            vpn_config.subscription_link = subscription_link

        await session.commit()

        # ======================================================
        # MESSAGE
        # ======================================================

        traffic_text = (
            "نامحدود"
            if plan.traffic_gb <= 0
            else f"{plan.traffic_gb} GB"
        )

        text = (
            "🎉 <b>خرید شما با موفقیت انجام شد!</b>\n\n"
            f"📦 <b>پلن:</b> {plan.name}\n"
            f"🌐 <b>سرور:</b> {panel.name}\n"
            f"📊 <b>حجم:</b> {traffic_text}\n"
            f"⏳ <b>مدت:</b> {plan.duration_days} روز\n"
            f"📱 <b>نام کانفیگ:</b> {email}\n\n"
            "🔗 <b>Subscription:</b>\n"
            f"<code>{subscription_link}</code>\n\n"
            f"📡 <b>تعداد کانفیگ‌های تکی:</b> "
            f"{len(subscription_links)}\n\n"
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