import uuid

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import get_vpn_config_by_order, save_vpn_config
from app.database.models import Order
from app.services.panel_manager import get_client
from app.services.sanaei_client import build_config_link
from app.utils import texts
from app.utils.qrcode_gen import generate_qr_bytes


async def provision_and_deliver(
    bot: Bot,
    session: AsyncSession,
    order: Order,
) -> None:
    """
    برای یک سفارش فقط یک کانفیگ ایجاد می‌کند.

    اگر کانفیگ قبلاً برای سفارش ساخته شده باشد،
    دوباره روی پنل client جدید ایجاد نمی‌کند و همان کانفیگ
    قبلی را برای کاربر ارسال می‌کند.
    """

    # --------------------------------------------------
    # جلوگیری از ساخت کانفیگ تکراری
    # --------------------------------------------------
    existing = await get_vpn_config_by_order(
        session,
        order.id,
    )

    if existing is not None:
        qr = generate_qr_bytes(existing.config_link)

        await bot.send_photo(
            chat_id=order.user.telegram_id,
            photo=BufferedInputFile(
                qr.read(),
                filename="config.png",
            ),
            caption=(
                f"{texts.ORDER_APPROVED_USER}\n\n"
                f"`{existing.config_link}`"
            ),
            parse_mode="Markdown",
        )
        return

    # --------------------------------------------------
    # اطلاعات پلن
    # --------------------------------------------------
    plan = order.plan

    if plan.panel_key not in settings.PANELS:
        raise RuntimeError(
            f"پنل «{plan.panel_key}» برای پلن "
            f"«{plan.name}» تعریف نشده است."
        )

    panel_cfg = settings.PANELS[plan.panel_key]
    client = get_client(plan.panel_key)

    # --------------------------------------------------
    # ساخت نام یکتا برای Client
    # --------------------------------------------------
    email = (
        f"tg{order.user.telegram_id}-"
        f"{uuid.uuid4().hex[:6]}"
    )

    # --------------------------------------------------
    # ساخت Client روی پنل
    # --------------------------------------------------
    result = await client.add_client(
        email=email,
        traffic_gb=plan.traffic_gb,
        duration_days=plan.duration_days,
        inbound_id=panel_cfg.inbound_id,
    )

    client_uuid = result["client_uuid"]

    config_link = build_config_link(
        panel_cfg,
        result["inbound"],
        client_uuid,
        email,
    )

    # --------------------------------------------------
    # ذخیره در دیتابیس
    # --------------------------------------------------
    cfg = await save_vpn_config(
            session,
            order=order,
            panel_key=plan.panel_key,
            inbound_id=panel_cfg.inbound_id,
            client_email=email,
            client_uuid=result["client_uuid"],
            config_link=config_link,
            traffic_gb=plan.traffic_gb,
            duration_days=plan.duration_days,
            plan_type=plan.plan_type,
            plan_name=plan.name,
            config_name=order.config_name or "کانفیگ من",
        )

    # جلوگیری از warning مربوط به متغیر استفاده‌نشده
    _ = cfg

    # --------------------------------------------------
    # ساخت QR
    # --------------------------------------------------
    qr = generate_qr_bytes(config_link)

    # --------------------------------------------------
    # ارسال به کاربر
    # --------------------------------------------------
    await bot.send_photo(
        chat_id=order.user.telegram_id,
        photo=BufferedInputFile(
            qr.read(),
            filename="config.png",
        ),
        caption=(
            f"{texts.ORDER_APPROVED_USER}\n\n"
            f"`{config_link}`"
        ),
        parse_mode="Markdown",
    )