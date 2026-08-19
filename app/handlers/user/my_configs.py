from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import get_or_create_user
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
# نکته: به‌جای اتکا به «user» تزریق‌شده توسط middleware (که معلوم نیست
# روی همه‌ی روترها/انواع هندلر فعال باشه)، دقیقاً مثل start.py خود
# کاربر رو مستقیم از دیتابیس می‌گیریم/می‌سازیم. این کار خطای
# «missing 1 required positional argument: 'user'» رو کاملاً حذف می‌کنه.
@router.message(Command("my_configs"))
async def my_configs_command(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await show_configs_list(message, user, session)


# ---------- هندلر دکمه «📂 کانفیگ‌های من» از منوی اصلی (Reply Keyboard) ----------
# این دکمه یک متن معمولی می‌فرسته (نه CallbackQuery)، برای همین باید
# با message/F.text گرفته بشه. اگر متن دقیق دکمه‌تون توی
# app/keyboards/user_kb.py چیز دیگه‌ایه، همین رشته رو با اون یکی عوض کنید.
@router.message(F.text == "📂 کانفیگ‌های من")
async def my_configs_button(message: types.Message, session: AsyncSession):
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await show_configs_list(message, user, session)


# ---------- هندلر دکمه «کانفیگ‌های من» به‌صورت اینلاین (در صورت استفاده جای دیگه) ----------
@router.callback_query(F.data == "my_configs")
async def my_configs_callback(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    await show_configs_list(callback.message, user, session)


# ---------- هندلر دکمه «بازگشت به منو» ----------
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery):
    await callback.answer()
    # اصلاح شد: مسیر و اسم درست تابع منو (طبق app/handlers/user/start.py)
    from app.keyboards.user_kb import main_menu_kb

    # منوی اصلی یک ReplyKeyboardMarkup هست، پس با edit_text قابل نمایش نیست
    # (edit_text فقط InlineKeyboardMarkup قبول می‌کنه). به همین خاطر پیام
    # قبلی رو حذف می‌کنیم و یک پیام جدید با کیبورد اصلی می‌فرستیم.
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "🏠 منوی اصلی",
        reply_markup=main_menu_kb(),
    )


# ---------- نمایش جزئیات یک کانفیگ خاص ----------
@router.callback_query(ConfigListCallback.filter())
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

            # تلگرام caption عکس رو حداکثر ۱۰۲۴ کاراکتر قبول می‌کنه.
            # اگه لینک ساب (مثلاً به‌خاطر داده‌ی قدیمی توی دیتابیس) بلند
            # باشه و caption از این حد رد بشه، عکس رو بدون caption
            # می‌فرستیم و متن رو جدا (پیام متنی محدودیتش خیلی بیشتره).
            if len(caption) > 1024:
                await callback.message.answer_photo(
                    photo=BufferedInputFile(bio.read(), filename="config_qr.png"),
                )
                await callback.message.answer(
                    caption,
                    reply_markup=back_to_menu_keyboard(),
                )
            else:
                await callback.message.answer_photo(
                    photo=BufferedInputFile(bio.read(), filename="config_qr.png"),
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
