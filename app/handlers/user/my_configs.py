from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import get_or_create_user, get_vpn_config, list_user_configs
from app.keyboards.user_kb import PLAN_TYPE_LABELS, my_configs_kb
from app.services.panel_manager import get_client
from app.utils import texts
from app.utils.qrcode_gen import generate_qr_bytes

router = Router(name="my_configs")


async def _usage_text(cfg) -> str:
    """
    تلاش می‌کند مصرف واقعی حجم را از پنل بگیرد؛ اگر پنل در دسترس نبود،
    فقط سقف حجم خریداری‌شده را نشان می‌دهد تا صفحه‌ی کاربر خراب نشود.
    """
    total = "نامحدود" if cfg.traffic_gb == 0 else f"{cfg.traffic_gb} گیگ"
    try:
        client = get_client(cfg.panel_key)
        traffic = await client.get_client_traffic(cfg.client_email)
        if traffic:
            used_bytes = int(traffic.get("up", 0)) + int(traffic.get("down", 0))
            used_gb = used_bytes / (1024 ** 3)
            return f"{used_gb:.1f} / {total} گیگ" if cfg.traffic_gb else f"{used_gb:.1f} گیگ مصرف‌شده (نامحدود)"
    except Exception:
        pass
    return f"از {total}"


def _expire_status(expire_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=timezone.utc)
    remaining = expire_at - now
    if remaining.total_seconds() <= 0:
        return "🔴 منقضی شده"
    days = remaining.days
    return f"🟢 {days} روز مانده ({expire_at.strftime('%Y-%m-%d')})"


@router.message(F.text == "📂 کانفیگ‌های من")
async def my_configs(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    configs = await list_user_configs(session, user.id)
    if not configs:
        await message.answer(texts.MY_CONFIGS_EMPTY)
        return

    status_msg = await message.answer("⏳ در حال بررسی وضعیت کانفیگ‌ها...")

    text = texts.MY_CONFIGS_HEADER.format(count=len(configs)) + "\n"
    for cfg in configs:
        panel = settings.PANELS.get(cfg.panel_key)
        expire_status = _expire_status(cfg.expire_at)
        usage = await _usage_text(cfg)
        text += texts.MY_CONFIGS_ITEM.format(
            status_emoji="🔴" if "منقضی" in expire_status else "🟢",
            id=cfg.id,
            panel_name=panel.name if panel else cfg.panel_key,
            type_label=PLAN_TYPE_LABELS.get(cfg.plan_type, ""),
            plan_name=cfg.plan_name or "-",
            usage=usage,
            expire_status=expire_status,
        )
        text += "\n"
    text += texts.MY_CONFIGS_FOOTER

    await status_msg.edit_text(text, reply_markup=my_configs_kb(configs))


@router.callback_query(F.data.startswith("show_config:"))
async def show_config(callback: CallbackQuery, session: AsyncSession) -> None:
    config_id = int(callback.data.split(":", 1)[1])
    cfg = await get_vpn_config(session, config_id)
    user = await get_or_create_user(
        session, callback.from_user.id, callback.from_user.username, callback.from_user.full_name
    )
    if cfg is None or cfg.user_id != user.id:
        await callback.answer(texts.CONFIG_NOT_FOUND, show_alert=True)
        return

    panel = settings.PANELS.get(cfg.panel_key)
    qr = generate_qr_bytes(cfg.config_link)
    await callback.message.answer_photo(
        photo=BufferedInputFile(qr.read(), filename="config.png"),
        caption=texts.CONFIG_QR_CAPTION.format(
            panel_name=panel.name if panel else cfg.panel_key,
            plan_name=cfg.plan_name or "-",
            link=cfg.config_link,
        ),
        parse_mode="Markdown",
    )
    await callback.answer()
