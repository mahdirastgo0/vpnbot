from __future__ import annotations

import json

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
    config_items_kb,
    main_menu_kb,
)
from app.utils import texts
from app.utils.callback_data import ConfigListCallback


router = Router()


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
    if (
        isinstance(
            vpn_config.config_link,
            str,
        )
        and vpn_config.config_link.startswith(
            (
                "vless://",
                "vmess://",
                "trojan://",
                "ss://",
                "hy2://",
                "hysteria://",
            )
        )
    ):
        return [
            vpn_config.config_link
        ]

    return []


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
            VpnConfig.user_id == user.id
        )
        .where(
            VpnConfig.expire_at > func.now()
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
        parse_mode="HTML",
    )


# ============================================================
# /my_configs
# ============================================================

@router.message(
    Command("my_configs")
)
async def my_configs_command(
    message: types.Message,
    session: AsyncSession,
):

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    await show_configs_list(
        message,
        user,
        session,
    )


# ============================================================
# دکمه کانفیگ‌های من
# ============================================================

@router.message(
    F.text == "📂 کانفیگ‌های من"
)
async def my_configs_button(
    message: types.Message,
    session: AsyncSession,
):

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

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

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

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

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    vpn_config = await session.get(
        VpnConfig,
        callback_data.config_id,
    )

    if not vpn_config:
        await callback.answer(
            "کانفیگ یافت نشد.",
            show_alert=True,
        )
        return

    if vpn_config.user_id != user.id:
        await callback.answer(
            "شما به این کانفیگ دسترسی ندارید.",
            show_alert=True,
        )
        return

    individual_links = get_individual_links(
        vpn_config
    )

    # اگر هیچ لینک تکی نداریم
    if not individual_links:
        await callback.message.edit_text(
            "❌ لینک کانفیگ تکی برای این سرویس پیدا نشد.\n\n"
            "می‌توانید Subscription را استفاده کنید.",
            reply_markup=back_to_menu_keyboard(),
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

    # ========================================================
    # نمایش اطلاعات سرویس و دکمه‌های کانفیگ تکی
    # ========================================================

    text = (
        "📱 <b>اطلاعات کانفیگ</b>\n\n"
        f"📌 <b>نام:</b> "
        f"{vpn_config.config_name}\n"
        f"📦 <b>پلن:</b> "
        f"{vpn_config.plan_name}\n"
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
        parse_mode="HTML",
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
        parts = callback.data.split(":")

        if len(parts) != 3:
            raise ValueError

        config_id = int(parts[1])
        index = int(parts[2])

    except (
        ValueError,
        TypeError,
    ):
        await callback.answer(
            "❌ اطلاعات کانفیگ نامعتبر است.",
            show_alert=True,
        )
        return

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    vpn_config = await session.get(
        VpnConfig,
        config_id,
    )

    if not vpn_config:
        await callback.answer(
            "❌ کانفیگ یافت نشد.",
            show_alert=True,
        )
        return

    if vpn_config.user_id != user.id:
        await callback.answer(
            "❌ شما به این کانفیگ دسترسی ندارید.",
            show_alert=True,
        )
        return

    individual_links = get_individual_links(
        vpn_config
    )

    if (
        index < 0
        or index >= len(individual_links)
    ):
        await callback.answer(
            "❌ لینک کانفیگ پیدا نشد.",
            show_alert=True,
        )
        return

    link = individual_links[index]

    # ========================================================
    # QR Code
    # ========================================================

    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            box_size=10,
            border=2,
        )

        qr.add_data(link)
        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black",
            back_color="white",
        )

        bio = BytesIO()

        img.save(
            bio,
            "PNG",
        )

        bio.seek(0)

        await callback.message.delete()

        caption = (
            "📱 <b>کانفیگ تکی</b>\n\n"
            f"📌 <b>نام:</b> "
            f"{vpn_config.config_name}\n"
            f"🔢 <b>کانفیگ:</b> "
            f"{index + 1}\n\n"
            "🔗 <b>لینک:</b>\n"
            f"<code>{link}</code>"
        )

        if len(caption) > 1024:

            await callback.message.answer_photo(
                photo=BufferedInputFile(
                    bio.read(),
                    filename="config_qr.png",
                ),
            )

            await callback.message.answer(
                caption,
                reply_markup=back_to_menu_keyboard(),
                parse_mode="HTML",
            )

        else:

            await callback.message.answer_photo(
                photo=BufferedInputFile(
                    bio.read(),
                    filename="config_qr.png",
                ),
                caption=caption,
                reply_markup=back_to_menu_keyboard(),
                parse_mode="HTML",
            )

    except ImportError:

        await callback.message.edit_text(
            "📱 <b>کانفیگ تکی</b>\n\n"
            f"📌 <b>نام:</b> "
            f"{vpn_config.config_name}\n\n"
            f"<code>{link}</code>",
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )

    await callback.answer()


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

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    vpn_config = await session.get(
        VpnConfig,
        config_id,
    )

    if not vpn_config:
        await callback.answer(
            "❌ کانفیگ یافت نشد.",
            show_alert=True,
        )
        return

    if vpn_config.user_id != user.id:
        await callback.answer(
            "❌ شما به این کانفیگ دسترسی ندارید.",
            show_alert=True,
        )
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

    # ========================================================
    # QR Subscription
    # ========================================================

    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            box_size=10,
            border=2,
        )

        qr.add_data(
            subscription_link
        )

        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black",
            back_color="white",
        )

        bio = BytesIO()

        img.save(
            bio,
            "PNG",
        )

        bio.seek(0)

        await callback.message.delete()

        caption = (
            "🔗 <b>Subscription</b>\n\n"
            f"📌 <b>نام کانفیگ:</b> "
            f"{vpn_config.config_name}\n\n"
            f"<code>{subscription_link}</code>"
        )

        if len(caption) > 1024:

            await callback.message.answer_photo(
                photo=BufferedInputFile(
                    bio.read(),
                    filename="subscription_qr.png",
                ),
            )

            await callback.message.answer(
                caption,
                reply_markup=back_to_menu_keyboard(),
                parse_mode="HTML",
            )

        else:

            await callback.message.answer_photo(
                photo=BufferedInputFile(
                    bio.read(),
                    filename="subscription_qr.png",
                ),
                caption=caption,
                reply_markup=back_to_menu_keyboard(),
                parse_mode="HTML",
            )

    except ImportError:

        await callback.message.edit_text(
            "🔗 <b>Subscription</b>\n\n"
            f"<code>{subscription_link}</code>",
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )

    await callback.answer()