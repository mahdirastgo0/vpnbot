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

    # ==========================================================
    # CLIENT
    # ==========================================================

    client = SanaeiClient(panel)

    try:

        # ------------------------------------------------------
        # Config name
        #
        # همان اسمی که کاربر هنگام خرید وارد کرده.
        # اگر به هر دلیل خالی باشد، یک نام یکتا می‌سازیم.
        # ------------------------------------------------------

        email = (
            order.config_name
            or f"user-{order.user.telegram_id}-{order.id}"
        ).strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ خالی است."
            )

        # ------------------------------------------------------
        # Traffic
        #
        # plan.traffic_gb:
        #   0 = unlimited
        # ------------------------------------------------------

        traffic_gb = int(
            plan.traffic_gb or 0
        )

        # ------------------------------------------------------
        # Duration
        # ------------------------------------------------------

        duration_days = int(
            plan.duration_days or 0
        )

        # ------------------------------------------------------
        # Inbound
        #
        # فقط اینباند انتخاب می‌شود.
        # حجم و زمان در Client قرار می‌گیرند.
        # ------------------------------------------------------

        inbound_id = int(
            panel.inbound_id
        )

        # ======================================================
        # CREATE CLIENT
        # ======================================================

        result = await client.add_client(
            email=email,
            traffic_gb=traffic_gb,
            duration_days=duration_days,
            inbound_id=inbound_id,
        )

        client_uuid = result["client_uuid"]

        inbound = result.get("inbound")

        if not inbound:
            raise SanaeiApiError(
                f"اینباند {inbound_id} بعد از ساخت کلاینت "
                "از پنل دریافت نشد."
            )

        # ======================================================
        # BUILD CONFIG LINK
        # ======================================================

        config_link = build_config_link(
            panel=panel,
            inbound=inbound,
            client_uuid=client_uuid,
            email=email,
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
        # USER
        # ======================================================

        user = order.user

        if user is None:
            raise SanaeiApiError(
                "کاربر سفارش پیدا نشد."
            )

        # ======================================================
        # TRAFFIC TEXT
        # ======================================================

        if traffic_gb <= 0:
            traffic_text = "نامحدود"
        else:
            traffic_text = f"{traffic_gb} GB"

        # ======================================================
        # SEND CONFIG
        # ======================================================

        text = (
            "🎉 <b>خرید شما با موفقیت انجام شد!</b>\n\n"
            f"📦 <b>پلن:</b> {plan.name}\n"
            f"🌐 <b>سرور:</b> {panel.name}\n"
            f"📊 <b>حجم:</b> {traffic_text}\n"
            f"⏳ <b>مدت:</b> {duration_days} روز\n"
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