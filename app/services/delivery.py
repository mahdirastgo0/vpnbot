from __future__ import annotations

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Order
from app.services.sanaei_client import (
    SanaeiApiError,
    SanaeiClient,
    build_config_link,
)


async def provision_and_deliver(
    bot: Bot,
    session: AsyncSession,
    order: Order,
) -> None:

    plan = order.plan

    if plan is None:
        raise SanaeiApiError(
            "پلن سفارش پیدا نشد."
        )

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        raise SanaeiApiError(
            f"پنل «{plan.panel_key}» پیدا نشد."
        )

    client = SanaeiClient(panel)

    try:

        # ------------------------------------------------------
        # Client name
        # ------------------------------------------------------

        email = (
            order.config_name
            or f"user-{order.user.telegram_id}-{order.id}"
        )

        # ------------------------------------------------------
        # Create client on panel
        # ------------------------------------------------------

        result = await client.add_client(
            email=email,
            traffic_gb=plan.traffic_gb,
            duration_days=plan.duration_days,
            inbound_id=panel.inbound_id,
            telegram_id=order.user.telegram_id,
        )

        client_uuid = result["client_uuid"]
        inbound = result["inbound"]

        # ------------------------------------------------------
        # Build config
        # ------------------------------------------------------

        config_link = build_config_link(
            panel=panel,
            inbound=inbound,
            client_uuid=client_uuid,
            email=email,
        )

        # ------------------------------------------------------
        # Save
        # ------------------------------------------------------

        if hasattr(order, "client_uuid"):
            order.client_uuid = client_uuid

        if hasattr(order, "config_link"):
            order.config_link = config_link

        if hasattr(order, "config_name"):
            order.config_name = email

        if hasattr(order, "panel_key"):
            order.panel_key = panel.key

        await session.commit()

        # ------------------------------------------------------
        # User
        # ------------------------------------------------------

        user = order.user

        if user is None:
            raise SanaeiApiError(
                "کاربر سفارش پیدا نشد."
            )

        # ------------------------------------------------------
        # Message
        # ------------------------------------------------------

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
            "🔐 <b>کانفیگ شما:</b>\n\n"
            f"<code>{config_link}</code>\n\n"
            "روی لینک بالا بزنید و آن را در کلاینت VPN خود وارد کنید."
        )

        await bot.send_message(
            user.telegram_id,
            text,
            parse_mode="HTML",
        )

    finally:

        await client.close()