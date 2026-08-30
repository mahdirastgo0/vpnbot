from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    User,
    UserTrial,
    Plan,
    Order,
    OrderStatus,
    PaymentMethod,
)

from app.database.crud import get_or_create_user
from app.services.delivery import provision_and_deliver


router = Router(name="trial")


# ============================================================
# 🎁 نمایش سرویس‌های تست رایگان
# ============================================================

@router.message(F.text == "🎁 سرویس تست رایگان")
async def get_free_trial(
    message: Message,
    session: AsyncSession,
) -> None:

    # --------------------------------------------------------
    # پیدا کردن / ساخت کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # مقادیر ساده را ذخیره می‌کنیم
    # تا بعداً بعد از rollback به Lazy Loading نخوریم.
    user_id = user.id
    telegram_id = user.telegram_id

    # --------------------------------------------------------
    # پیدا کردن تمام پلن‌های تست فعال
    # --------------------------------------------------------

    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
    )

    plans = list(result.scalars().all())

    print(
        "TRIAL DEBUG:",
        "user_id=", user_id,
        "telegram_id=", telegram_id,
        "plans=",
        [
            (
                p.id,
                p.panel_key,
                p.is_trial,
                p.is_active,
            )
            for p in plans
        ],
    )

    # --------------------------------------------------------
    # هیچ پلن تستی وجود ندارد
    # --------------------------------------------------------

    if not plans:
        await message.answer(
            "❌ در حال حاضر هیچ سرویس تستی در دسترس نیست."
        )
        return

    # --------------------------------------------------------
    # پیدا کردن تست‌هایی که کاربر هنوز استفاده نکرده
    # --------------------------------------------------------

    available_plans = []

    for plan in plans:

        result = await session.execute(
            select(UserTrial).where(
                UserTrial.user_id == user_id,
                UserTrial.panel_key == plan.panel_key,
                UserTrial.used.is_(True),
            )
        )

        already_used = result.scalar_one_or_none()

        print(
            "TRIAL CHECK:",
            "user_id=", user_id,
            "panel=", plan.panel_key,
            "already_used=", already_used,
        )

        if already_used is None:
            available_plans.append(plan)

    # --------------------------------------------------------
    # همه تست‌ها قبلاً استفاده شده‌اند
    # --------------------------------------------------------

    if not available_plans:

        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید.\n\n"
            "هر کاربر برای هر سرور فقط یک بار می‌تواند تست دریافت کند."
        )

        return

    # --------------------------------------------------------
    # ساخت کیبورد انتخاب سرور
    # --------------------------------------------------------

    builder = InlineKeyboardBuilder()

    for plan in available_plans:

        # نام خواناتر برای پنل‌ها
        if plan.panel_key == "ir1":
            title = "🇮🇷 ایران - تانل"

        elif plan.panel_key == "pol":
            title = "🇵🇱 لهستان - مستقیم"

        else:
            title = f"🌐 {plan.panel_key}"

        # محاسبه حجم
        if plan.traffic_mb:
            traffic = f"{plan.traffic_mb} MB"

        elif plan.traffic_gb <= 0:
            traffic = "نامحدود"

        else:
            traffic = f"{plan.traffic_gb} GB"

        builder.button(
            text=(
                f"{title} | "
                f"{traffic} | "
                f"{plan.duration_days} روز"
            ),
            callback_data=f"trial_select:{plan.id}",
        )

    builder.adjust(1)

    # --------------------------------------------------------
    # نمایش انتخاب به کاربر
    # --------------------------------------------------------

    await message.answer(
        "🎁 <b>سرویس تست رایگان</b>\n\n"
        "لطفاً سروری که می‌خواهید تست کنید را انتخاب کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ============================================================
# 🎯 انتخاب تست توسط کاربر
# ============================================================

@router.callback_query(F.data.startswith("trial_select:"))
async def select_trial(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    # --------------------------------------------------------
    # دریافت Plan ID از callback
    # --------------------------------------------------------

    try:

        plan_id = int(
            callback.data.split(":", 1)[1]
        )

    except (ValueError, AttributeError):

        print(
            "TRIAL CALLBACK INVALID:",
            callback.data,
        )

        await callback.answer(
            "❌ انتخاب نامعتبر است.",
            show_alert=True,
        )

        return

    print(
        "TRIAL CALLBACK:",
        "data=", callback.data,
        "plan_id=", plan_id,
        "telegram_id=", callback.from_user.id,
    )

    # --------------------------------------------------------
    # پیدا کردن کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    user_id = user.id
    telegram_id = user.telegram_id

    # --------------------------------------------------------
    # پیدا کردن پلن انتخاب‌شده
    # --------------------------------------------------------

    result = await session.execute(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
    )

    plan = result.scalar_one_or_none()

    # Debug
    print(
        "TRIAL PLAN RESULT:",
        "plan_id=", plan_id,
        "plan=", plan,
    )

    if plan is not None:

        print(
            "TRIAL PLAN DATA:",
            "id=", plan.id,
            "panel=", plan.panel_key,
            "is_trial=", plan.is_trial,
            "is_active=", plan.is_active,
        )

    # --------------------------------------------------------
    # پلن وجود ندارد / غیرفعال است
    # --------------------------------------------------------

    if plan is None:

        await callback.answer(
            "❌ این سرویس تست دیگر در دسترس نیست.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # بررسی مجدد مصرف تست
    #
    # این بررسی مهم است چون ممکن است کاربر دو بار
    # روی دکمه کلیک کند.
    # --------------------------------------------------------

    result = await session.execute(
        select(UserTrial).where(
            UserTrial.user_id == user_id,
            UserTrial.panel_key == plan.panel_key,
            UserTrial.used.is_(True),
        )
    )

    already_used = result.scalar_one_or_none()

    print(
        "TRIAL SELECT CHECK:",
        "user_id=", user_id,
        "panel=", plan.panel_key,
        "already_used=", already_used,
    )

    if already_used is not None:

        await callback.answer(
            "❌ شما قبلاً تست این سرور را دریافت کرده‌اید.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # تأیید Callback
    # --------------------------------------------------------

    await callback.answer()

    # --------------------------------------------------------
    # حذف دکمه‌های انتخاب
    # --------------------------------------------------------

    try:

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # محاسبه حجم
    # --------------------------------------------------------

    if plan.traffic_mb:

        traffic_text = f"{plan.traffic_mb} MB"

    elif plan.traffic_gb <= 0:

        traffic_text = "نامحدود"

    else:

        traffic_text = f"{plan.traffic_gb} GB"

    # --------------------------------------------------------
    # نام کانفیگ
    #
    # فعلاً همان نام قبلی را نگه می‌داریم.
    # بعداً می‌توانیم UUID اضافه کنیم.
    # --------------------------------------------------------

    config_name = (
        f"Trial-{plan.panel_key}-{telegram_id}"
    )

    # --------------------------------------------------------
    # اطلاع به کاربر
    # --------------------------------------------------------

    await callback.message.answer(
        "⏳ <b>در حال ساخت سرویس تست شما...</b>\n\n"
        f"🌐 <b>سرور:</b> {plan.panel_key}\n"
        f"📦 <b>حجم:</b> {traffic_text}\n"
        f"⏱ <b>مدت:</b> {plan.duration_days} روز",
        parse_mode="HTML",
    )

    # --------------------------------------------------------
    # ساخت سفارش
    # --------------------------------------------------------

    order = Order(
        user_id=user_id,
        plan_id=plan.id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=config_name,
    )

    session.add(order)

    await session.commit()

    await session.refresh(order)

    # --------------------------------------------------------
    # جلوگیری از Lazy Loading
    # --------------------------------------------------------

    order.user = user
    order.plan = plan

    # --------------------------------------------------------
    # ساخت سرویس در پنل
    # --------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=callback.bot,
            session=session,
            order=order,
        )

    except Exception as e:

        # اطلاعات ساده قبل از rollback
        error_user_id = user_id
        error_panel = plan.panel_key

        print(
            "TRIAL PROVISION ERROR:",
            f"user={error_user_id}",
            f"panel={error_panel}",
            f"error={e}",
        )

        # rollback
        await session.rollback()

        # ----------------------------------------------------
        # اطلاع به کاربر
        # ----------------------------------------------------

        await callback.message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت مصرف تست
    #
    # فقط وقتی ساخت سرویس با موفقیت انجام شده.
    # --------------------------------------------------------

    trial = UserTrial(
        user_id=user_id,
        panel_key=plan.panel_key,
        used=True,
    )

    session.add(trial)

    try:

        await session.commit()

    except Exception as e:

        await session.rollback()

        print(
            "TRIAL SAVE ERROR:",
            f"user={user_id}",
            f"panel={plan.panel_key}",
            f"error={e}",
        )

        await callback.message.answer(
            "⚠️ سرویس ساخته شد، اما ثبت وضعیت تست با مشکل مواجه شد.\n"
            "لطفاً با پشتیبانی تماس بگیرید."
        )

        return

    # --------------------------------------------------------
    # لاگ نهایی
    # --------------------------------------------------------

    print(
        "TRIAL CREATED:",
        f"user={user_id}",
        f"telegram_id={telegram_id}",
        f"panel={plan.panel_key}",
        f"plan_id={plan.id}",
        f"order_id={order.id}",
    )

