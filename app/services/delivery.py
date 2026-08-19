import uuid

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import save_vpn_config
from app.database.models import Order
from app.services.panel_manager import get_client
from app.services.sanaei_client import build_config_link
from app.utils import texts
from app.utils.qrcode_gen import generate_qr_bytes


async def provision_and_deliver(bot: Bot, session: AsyncSession, order: Order) -> None:
    """
    بعد از تایید قطعی پرداخت (توسط زرین‌پال یا ادمین) صدا زده می‌شود:
    روی پنل مربوطه یک کلاینت جدید می‌سازد و لینک کانفیگ را برای کاربر ارسال می‌کند.
    """
    plan = order.plan
    panel_cfg = settings.PANELS[plan.panel_key]
    client = get_client(plan.panel_key)

    email = f"tg{order.user.telegram_id}-{uuid.uuid4().hex[:6]}"
    result = await client.add_client(
        email=email,
        traffic_gb=plan.traffic_gb,
        duration_days=plan.duration_days,
        inbound_id=panel_cfg.inbound_id,
    )
    config_link = build_config_link(panel_cfg, result["inbound"], result["client_uuid"], email)

    await save_vpn_config(
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
    )

    qr = generate_qr_bytes(config_link)
    await bot.send_photo(
        chat_id=order.user.telegram_id,
        photo=BufferedInputFile(qr.read(), filename="config.png"),
        caption=f"{texts.ORDER_APPROVED_USER}\n\n`{config_link}`",
        parse_mode="Markdown",
    )
