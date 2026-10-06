from __future__ import annotations

import json
from html import escape

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
)
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import get_or_create_user
from app.database.models import User, VpnConfig
from app.keyboards.inline import (
    config_list_keyboard,
    back_to_menu_keyboard,
)
from app.keyboards.user_kb import (
    BTN_MY_CONFIGS,
    config_items_kb,
    main_menu_kb,
)
from app.utils.callback_data import ConfigListCallback
from app.utils.qrcode_gen import generate_qr_bytes


router = Router()

_LINK_PREFIXES = (
    "vless://",
    "vmess://",
    "trojan://",
    "ss://",
    "hy2://",
    "hysteria://",
)


# ============================================================
# ابزار
# ============================================================

def get_individual_links(
    vpn_config: VpnConfig,
) -> list[str]:

    if not vpn_config.config_link:
        return []

    try:
        data = json.loads(
            vpn_config.config_link
        )

        if isinstance(data, list):
            return [
                link
                for link in data
                if isinstance(link, str)
                and link.strip()
            ]

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        pass

    # برای داده‌های قدیمی
    if vpn_config.config_link.startswith(_LINK_PREFIXES):
        return [
            vpn_config.config_link
        ]

    return []


async def _get_user(
    session: AsyncSession,
    from_user: types.User,
) -> User:

    return await get_or_create_user(
        session,
        telegram_id=from_user.id,
        username=from_user.username,
        full_name=from_user.full_name,
    )


async def _get_owned_config(
    callback: CallbackQuery,
    session: AsyncSession,
    config_id: int,
) -> VpnConfig | None:
    """کانفیگ را برمی‌گرداند؛ اگر نبود یا مال کاربر نبود، alert می‌دهد."""

    user = await _get_user(session, callback.from_user)

    vpn_config = await session.get(
        VpnConfig,
        config_id,
    )

    if not vpn_config:
        await callback.answer(
            "❌ کانفیگ یافت نشد.",
            show_alert=True,
        )
        return None

    if vpn_config.user_id != user.id:
        await callback.answer(
            "❌ شما به این کانفیگ دسترسی ندارید.",
            show_alert=True,
        )
        return None

    return vpn_config


async def _send_qr(
    callback: CallbackQuery,
    data: str,
    caption: str,
    filename: str,
) -> None:

    photo = BufferedInputFile(
        generate_qr_bytes(data).read(),
        filename=filename,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    # کپشن عکس حداکثر ۱۰۲۴ کاراکتر است
    if len(caption) > 1024:

        await callback.message.answer_photo(photo=photo)

        await callback.message.answer(
            caption,
            reply_markup=back_to_menu_keyboard(),
        )

    else:

        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=back_to_menu_keyboard(),
        )


# ============================================================
# نمایش لیست کانفیگ‌ها
# ============================================================

async def show_configs_list(
    message: types.Message,
    user: User,
    session: AsyncSession,
):

    stmt = (
        select(VpnConfig)
        .where(
            VpnConfig.user_id == user.id,
            VpnConfig.expire_at > func.now(),
        )
        .order_by(
            VpnConfig.created_at.desc()
        )
    )

    configs = (
        await session.execute(stmt)
    ).scalars().all()

    if not configs:
        await message.answer(
            "📭 شما هیچ کانفیگ فعالی ندارید.\n"
            "برای خرید از بخش "
            "«🛒 خرید سرویس» اقدام کنید.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await message.answer(
        "📂 <b>کانفیگ‌های فعال شما:</b>\n\n"
        "یکی را انتخاب کنید.",
        reply_markup=config_list_keyboard(
            configs
        ),
    )


# ============================================================
# /my_configs و دکمه کانفیگ‌های من
# ============================================================

@router.message(Command("my_configs"))
@router.message(F.text == BTN_MY_CONFIGS)
async def my_configs_message(
    message: types.Message,
    session: AsyncSession,
):

    user = await _get_user(session, message.from_user)

    await show_configs_list(
        message,
        user,
        session,
    )


# ============================================================
# callback کانفیگ‌های من
# ============================================================

@router.callback_query(
    F.data == "my_configs"
)
async def my_configs_callback(
    callback: CallbackQuery,
    session: AsyncSession,
):

    await callback.answer()

    user = await _get_user(session, callback.from_user)

    await show_configs_list(
        callback.message,
        user,
        session,
    )


# ============================================================
# بازگشت به منو
# ============================================================

@router.callback_query(
    F.data == "back_to_menu"
)
async def back_to_menu_callback(
    callback: CallbackQuery,
):

    await callback.answer()

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "🏠 منوی اصلی",
        reply_markup=main_menu_kb(),
    )


# ============================================================
# نمایش یک کانفیگ
# ============================================================

@router.callback_query(
    ConfigListCallback.filter()
)
async def show_config(
    callback: CallbackQuery,
    callback_data: ConfigListCallback,
    session: AsyncSession,
):

    vpn_config = await _get_owned_config(
        callback,
        session,
        callback_data.config_id,
    )

    if vpn_config is None:
        return

    individual_links = get_individual_links(
        vpn_config
    )

    # اگر هیچ لینک تکی نداریم، فقط Subscription را نشان می‌دهیم
    if not individual_links:
        await callback.message.edit_text(
            "❌ لینک کانفیگ تکی برای این سرویس پیدا نشد.\n\n"
            "می‌توانید Subscription را استفاده کنید.",
            reply_markup=config_items_kb(vpn_config.id, 0),
        )

        await callback.answer()
        return

    traffic_text = (
        "نامحدود"
        if vpn_config.traffic_gb <= 0
        else f"{vpn_config.traffic_gb} GB"
    )

    expire_text = (
        vpn_config.expire_at.strftime(
            "%Y-%m-%d %H:%M"
        )
        if vpn_config.expire_at
        else "نامحدود"
    )

    text = (
        "📱 <b>اطلاعات کانفیگ</b>\n\n"
        f"📌 <b>نام:</b> "
        f"{escape(vpn_config.config_name)}\n"
        f"📦 <b>پلن:</b> "
        f"{escape(vpn_config.plan_name)}\n"
        f"📊 <b>حجم:</b> "
        f"{traffic_text}\n"
        f"⏳ <b>انقضا:</b> "
        f"{expire_text}\n\n"
        f"📡 <b>تعداد کانفیگ تکی:</b> "
        f"{len(individual_links)}\n\n"
        "یکی از کانفیگ‌های تکی را انتخاب کنید:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=config_items_kb(
            vpn_config.id,
            len(individual_links),
        ),
    )

    await callback.answer()


# ============================================================
# نمایش کانفیگ تکی
# ============================================================

@router.callback_query(
    F.data.startswith("single_config:")
)
async def show_single_config(
    callback: CallbackQuery,
    session: AsyncSession,
):

    try:
        _, raw_config_id, raw_index = callback.data.split(":")
        config_id = int(raw_config_id)
        index = int(raw_index)

    except ValueError:
        await callback.answer(
            "❌ اطلاعات کانفیگ نامعتبر است.",
            show_alert=True,
        )
        return

    vpn_config = await _get_owned_config(
        callback,
        session,
        config_id,
    )

    if vpn_config is None:
        return

    individual_links = get_individual_links(
        vpn_config
    )

    if not 0 <= index < len(individual_links):
        await callback.answer(
            "❌ لینک کانفیگ پیدا نشد.",
            show_alert=True,
        )
        return

    link = individual_links[index]

    await callback.answer()

    await _send_qr(
        callback,
        link,
        (
            "📱 <b>کانفیگ تکی</b>\n\n"
            f"📌 <b>نام:</b> "
            f"{escape(vpn_config.config_name)}\n"
            f"🔢 <b>کانفیگ:</b> "
            f"{index + 1}\n\n"
            "🔗 <b>لینک:</b>\n"
            f"<code>{escape(link)}</code>"
        ),
        "config_qr.png",
    )


# ============================================================
# نمایش Subscription
# ============================================================

@router.callback_query(
    F.data.startswith("show_subscription:")
)
async def show_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
):

    try:
        config_id = int(
            callback.data.split(":")[1]
        )

    except (
        ValueError,
        IndexError,
    ):
        await callback.answer(
            "❌ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    vpn_config = await _get_owned_config(
        callback,
        session,
        config_id,
    )

    if vpn_config is None:
        return

    subscription_link = (
        vpn_config.subscription_link
    )

    if not subscription_link:
        await callback.answer(
            "❌ Subscription موجود نیست.",
            show_alert=True,
        )
        return

    await callback.answer()

    await _send_qr(
        callback,
        subscription_link,
        (
            "🔗 <b>Subscription</b>\n\n"
            f"📌 <b>نام کانفیگ:</b> "
            f"{escape(vpn_config.config_name)}\n\n"
            f"<code>{escape(subscription_link)}</code>"
        ),
        "subscription_qr.png",
    )
