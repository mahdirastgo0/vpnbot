from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, VpnConfig
from app.keyboards.inline import config_list_keyboard, back_to_menu_keyboard
from app.utils import texts
from app.utils.callback_data import ConfigListCallback

router = Router()  # <-- حتماً این خط را داشته باشید


@router.message(Command("my_configs"))
async def my_configs_command(message: types.Message, user: User, session: AsyncSession):
    """نمایش لیست کانفیگ‌های فعال کاربر"""
    stmt = (
        select(VpnConfig)
        .where(VpnConfig.user_id == user.id)
        .where(VpnConfig.expire_at > func.now())
        .order_by(VpnConfig.created_at.desc())
    )
    configs = (await session.execute(stmt)).scalars().all()

    if not configs:
        await message.answer(
            "📭 شما هیچ کانفیگ فعالی ندارید.\n"
            "برای خرید از بخش «🛒 خرید اشتراک» اقدام کنید.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await message.answer(
        "📂 کانفیگ‌های فعال شما:\n"
        "یکی را انتخاب کنید تا اطلاعات کامل آن را ببینید.",
        reply_markup=config_list_keyboard(configs),
    )


@router.callback_query(ConfigListCallback.filter())
async def show_config(
    callback: CallbackQuery,
    callback_data: ConfigListCallback,
    session: AsyncSession,
    user: User,
):
    """نمایش جزییات یک کانفیگ مشخص"""
    vpn_config = await session.get(VpnConfig, callback_data.config_id)
    if not vpn_config:
        await callback.answer("کانفیگ یافت نشد.", show_alert=True)
        return

    if vpn_config.user_id != user.id:
        await callback.answer("شما به این کانفیگ دسترسی ندارید.", show_alert=True)
        return

    # ---------- ساخت متن ----------
    traffic_text = "نامحدود" if vpn_config.traffic_gb <= 0 else f"{vpn_config.traffic_gb} GB"
    expire_text = vpn_config.expire_at.strftime("%Y-%m-%d %H:%M") if vpn_config.expire_at else "نامحدود"

    # استفاده از config_name (که در VpnConfig وجود دارد)
    caption = texts.CONFIG_QR_CAPTION.format(
        config_name=vpn_config.config_name,          # <-- کلید صحیح
        plan_name=vpn_config.plan_name,
        traffic_gb=traffic_text,
        expire_at=expire_text,
        subscription_link=vpn_config.subscription_link or "ندارد",
        # در صورت نیاز فیلدهای دیگر
    )

    # ---------- ارسال QR ----------
    if vpn_config.subscription_link:
        try:
            import qrcode
            from io import BytesIO

            qr = qrcode.QRCode(box_size=10, border=2)
            qr.add_data(vpn_config.subscription_link)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            bio = BytesIO()
            img.save(bio, "PNG")
            bio.seek(0)

            await callback.message.delete()
            await callback.message.answer_photo(
                photo=InputFile(bio, filename="config_qr.png"),
                caption=caption,
                reply_markup=back_to_menu_keyboard(),
            )
        except ImportError:
            # اگر qrcode نصب نیست، فقط لینک را نمایش بده
            await callback.message.edit_text(
                caption,
                reply_markup=back_to_menu_keyboard(),
            )
    else:
        await callback.message.edit_text(
            caption,
            reply_markup=back_to_menu_keyboard(),
        )

    await callback.answer()