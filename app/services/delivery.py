from __future__ import annotations

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Order
from app.services.sanaei_client import (
    SanaeiApiError,
    SanaeiClient,
)


async def provision_and_deliver(
    bot: Bot,
    session: AsyncSession,
    order: Order,
) -> None:

    # ==========================================================
    # PLAN
    # ==========================================================

    plan = order.plan

    if plan is None:

        raise SanaeiApiError(
            "پلن سفارش پیدا نشد."
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

    client = SanaeiClient(panel)

    try:

        # ======================================================
        # EMAIL / CONFIG NAME
        # ======================================================

        email = (
            order.config_name
            or f"user-{order.user.telegram_id}-{order.id}"
        )

        # ======================================================
        # CREATE CLIENT
        #
        # inbound:
        # ایران = 8
        # لهستان = 2
        #
        # حجم و زمان از خود Plan می‌آید.
        # ======================================================

        result = await client.add_client(

            email=email,

            traffic_gb=plan.traffic_gb,

            duration_days=plan.duration_days,

            inbound_id=panel.inbound_id,
        )

        client_uuid = result[
            "client_uuid"
        ]

        sub_id = result[
            "sub_id"
        ]

        inbound_id = result[
            "inbound_id"
        ]

        # ======================================================
        # IMPORTANT
        #
        # لینک را خود پنل می‌سازد.
        #
        # GET:
        #
        # /panel/api/clients/subLinks/{subId}
        #
        # ======================================================

        config_link = (
            await client.get_subscription_link(
                sub_id
            )
        )

        # ======================================================
        # SAVE ORDER
        # ======================================================

        if hasattr(order, "client_uuid"):

            order.client_uuid = client_uuid

        if hasattr(order, "config_link"):

            order.config_link = config_link

        if hasattr(order, "config_name"):

            order.config_name = email

        if hasattr(order, "panel_key"):

            order.panel_key = panel.key

        await session.commit()

        # ======================================================
        # SAVE VPN CONFIG
        # ======================================================

        vpn_config = getattr(
            order,
            "vpn_config",
            None,
        )

        if vpn_config is not None:

            vpn_config.panel_key = panel.key

            vpn_config.plan_type = plan.plan_type

            vpn_config.plan_name = plan.name

            vpn_config.config_name = email

            vpn_config.inbound_id = inbound_id

            vpn_config.client_email = email

            vpn_config.client_uuid = client_uuid

            vpn_config.config_link = config_link

            vpn_config.traffic_gb = plan.traffic_gb

            await session.commit()

        # ======================================================
        # SEND TO USER
        # ======================================================

        user = order.user

        if user is None:

            raise SanaeiApiError(
                "کاربر سفارش پیدا نشد."
            )

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

            f"⏳ <b>مدت:</b> "
            f"{plan.duration_days} روز\n"

            f"📱 <b>نام کانفیگ:</b> "
            f"{email}\n\n"

            "🔗 <b>لینک اشتراک شما:</b>\n\n"

            f"<code>{config_link}</code>\n\n"

            "این لینک را داخل کلاینت VPN خود وارد کنید."
        )

        await bot.send_message(

            user.telegram_id,

            text,

            parse_mode="HTML",
        )

    finally:

        await client.close()