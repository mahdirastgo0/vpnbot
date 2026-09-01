from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

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
        raise SanaeiApiError(
            f"پنل «{plan.panel_key}» پیدا نشد."
        )

    # ============================================================
    # نام کانفیگ
    # ============================================================

    email = (
        (order.config_name or "").strip()
        or f"user-{user.telegram_id}-{order.id}"
    )

    print(
        f"DEBUG CONFIG NAME | "
        f"order_id={order.id} | "
        f"order.config_name={order.config_name!r} | "
        f"email={email!r}"
    )

    client = SanaeiClient(panel)

    try:
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
        sub_id = result["sub_id"]

        subscription_link = result.get(
            "subscription_link"
        )

        subscription_links = result.get(
            "subscription_links",
            [],
        )

        individual_links = result.get(
            "individual_links",
            [],
        )

        # ========================================================
        # اضافه کردن نام انتخابی کاربر به لینک تکی
        # ========================================================

        config_name_fragment = quote(
            email,
            safe="",
        )

        formatted_individual_links = []

        for link in individual_links:

            if not isinstance(link, str):
                continue

            link = link.strip()

            if not link:
                continue

            # اگر لینک قبلاً # داشته باشد،
            # نام قبلی حذف می‌شود و نام جدید جایگزین می‌شود.
            link_without_fragment = link.split(
                "#",
                1,
            )[0]

            final_link = (
                f"{link_without_fragment}"
                f"#{config_name_fragment}"
            )

            formatted_individual_links.append(
                final_link
            )

        individual_links = formatted_individual_links

        print(
            f"DEBUG INDIVIDUAL LINKS | "
            f"count={len(individual_links)} | "
            f"links={individual_links}"
        )

        # ========================================================
        # ذخیره لینک‌های تکی
        #
        # config_link یک Text است، بنابراین لینک‌ها را
        # به صورت JSON ذخیره می‌کنیم.
        # ========================================================

        config_links_data = json.dumps(
            individual_links,
            ensure_ascii=False,
        )

        # ========================================================
        # تاریخ انقضا
        # ========================================================

        expire_at = (
            datetime.now(timezone.utc)
            + timedelta(days=plan.duration_days)
        )

        # ========================================================
        # ذخیره کانفیگ در دیتابیس
        # ========================================================

        vpn_config = VpnConfig(
            order_id=order.id,
            user_id=user.id,
            panel_key=panel.key,
            plan_type=plan.plan_type,
            plan_name=plan.name,

            # همان اسمی که کاربر انتخاب کرده
            config_name=email,

            inbound_id=panel.inbound_id,

            # email/client name پنل
            client_email=email,

            client_uuid=client_uuid,

            # لینک‌های تکی
            config_link=config_links_data,

            traffic_gb=plan.traffic_gb,

            expire_at=expire_at,

            # Subscription جداگانه ذخیره می‌شود
            subscription_link=subscription_link,
        )

        session.add(vpn_config)

        await session.commit()

        # ========================================================
        # متن حجم
        # ========================================================

        if plan.is_trial and plan.traffic_mb:
            traffic_text = (
                f"{plan.traffic_mb} MB"
            )

        elif plan.traffic_gb <= 0:
            traffic_text = "نامحدود"

        else:
            traffic_text = (
                f"{plan.traffic_gb} GB"
            )

        # ========================================================
        # عنوان پیام
        # ========================================================

        title = (
            "🎁 <b>سرویس تست رایگان شما آماده شد!</b>"
            if plan.is_trial
            else "🎉 <b>خرید شما با موفقیت انجام شد!</b>"
        )

        # ========================================================
        # پیام تحویل سرویس
        # ========================================================

        text = (
            f"{title}\n\n"
            f"📦 <b>پلن:</b> {plan.name}\n"
            f"🌐 <b>سرور:</b> {panel.name}\n"
            f"📊 <b>حجم:</b> {traffic_text}\n"
            f"⏳ <b>مدت:</b> {plan.duration_days} روز\n"
            f"📱 <b>نام کانفیگ:</b> {email}\n\n"
            f"📡 <b>تعداد کانفیگ‌های تکی:</b> "
            f"{len(individual_links)}\n\n"
            "🔗 <b>Subscription:</b>\n"
            f"<code>{subscription_link or 'ندارد'}</code>\n\n"
            "از بخش «📂 کانفیگ‌های من» می‌توانید "
            "کانفیگ تکی یا Subscription را دریافت کنید."
        )

        await bot.send_message(
            user.telegram_id,
            text,
            parse_mode="HTML",
        )

    finally:
        await client.close()