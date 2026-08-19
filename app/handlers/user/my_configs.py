from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, VpnConfig
from app.keyboards.inline import config_list_keyboard, back_to_menu_keyboard
from app.utils import texts
from app.utils.callback_data import ConfigListCallback

router = Router()


# ---------- نمایش لیست کانفیگ‌ها (مشترک) ----------
async def show_configs_list(message: types.Message, user: User, session: AsyncSession):
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


# ---------- هندلر دستور /my_configs ----------
@router.message(Command("my_configs"))
async def my_configs_command(message: types.Message, user: User, session: AsyncSession):
    await show_configs_list(message, user, session)


# ---------- هندلر دکمه «کانفیگ‌های من» از منوی اصلی ----------
@router.callback_query(F.data == "my_configs")
async def my_configs_callback(callback: CallbackQuery, user: User, session: AsyncSession):
    await callback.answer()
    await show_configs_list(callback.message, user, session)


# ---------- هندلر دکمه «بازگشت به منو» ----------
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery):
    await callback.answer()
    from app.keyboards.main_menu import main_menu_keyboard  # فرض بر این است که این تابع وجود دارد
    await callback.message.edit_text(
        "🏠 منوی اصلی",
        reply_markup=main_menu_keyboard(),
    )
    # اگر ویرایش ممکن نیست، پیام جدید بفرستید
    # await callback.message.delete()
    # await callback.message.answer("🏠 منوی اصلی", reply_markup=main_menu_keyboard())


# ---------- نمایش جزئیات یک کانفیگ خاص ----------
@router.callback_query(ConfigListCallback.filter())
async def show_config(
    callback: CallbackQuery,
    callback_data: ConfigListCallback,
    session: AsyncSession,
    user: User,
):
    vpn_config = await session.get(VpnConfig, callback_data.config_id)
    if not vpn_config:
        await callback.answer("کانفیگ یافت نشد.", show_alert=True)
        return

    if vpn_config.user_id != user.id:
        await callback.answer("شما به این کانفیگ دسترسی ندارید.", show_alert=True)
        return

    traffic_text = "نامحدود" if vpn_config.traffic_gb <= 0 else f"{vpn_config.traffic_gb} GB"
    expire_text = vpn_config.expire_at.strftime("%Y-%m-%d %H:%M") if vpn_config.expire_at else "نامحدود"

    caption = texts.CONFIG_QR_CAPTION.format(
        config_name=vpn_config.config_name,
        plan_name=vpn_config.plan_name,
        traffic_gb=traffic_text,
        expire_at=expire_text,
        subscription_link=vpn_config.subscription_link or "ندارد",
    )

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


# ---------- هندلر پیش‌فرض برای کال‌بک‌های ناشناخته ----------
# باید همیشه آخرین هندلر ثبت‌شده در این روتر باشد،
# چون بدون فیلتره و هر کال‌بکی رو قبل از رسیدن به هندلرهای
# پایین‌ترش قاپ می‌زنه.
@router.callback_query()
async def unknown_callback(callback: CallbackQuery):
    await callback.answer("این گزینه در دسترس نیست.", show_alert=True)
