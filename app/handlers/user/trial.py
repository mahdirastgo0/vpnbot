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
# HELPERS
# ============================================================

def get_trial_traffic_text(plan: Plan) -> str:

    if plan.traffic_mb:
        return f"{plan.traffic_mb} MB"

    if plan.traffic_gb <= 0:
        return "نامحدود"

    return f"{plan.traffic_gb} GB"


def get_panel_title(panel_key: str) -> str:

    if panel_key == "ir1":
        return "🇮🇷 ایران - تانل"

    if panel_key == "pol":
        return "🇵🇱 لهستان - مستقیم"

    return f"🌐 {panel_key}"


# ============================================================
# 🎁 سرویس تست رایگان
# ============================================================

@router.message(F.text == "🎁 سرویس تست رایگان")
async def get_free_trial(
    message: Message,
    session: AsyncSession,
) -> None:

    telegram_id = message.from_user.id

    # --------------------------------------------------------
    # گرفتن / ساخت کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=telegram_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # ID را جدا نگه می‌داریم
    # تا بعداً بعد از commit با MissingGreenlet مواجه نشویم.
    user_id = user.id

    # --------------------------------------------------------
    # گرفتن تمام پلن‌های تست فعال
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
        "========== TRIAL MENU =========="
    )

    print(
        "TRIAL MENU USER:",
        user_id,
        telegram_id,
    )

    print(
        "TRIAL MENU PLANS:",
        [
            {
                "id": p.id,
                "panel": p.panel_key,
                "trial": p.is_trial,
                "active": p.is_active,
                "name": p.name,
            }
            for p in plans
        ],
    )

    print(
        "================================"
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
    # فقط تست‌هایی که قبلاً مصرف نشده‌اند
    # --------------------------------------------------------

    available_plans: list[Plan] = []

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
            "plan_id=", plan.id,
            "already_used=", already_used,
        )

        if already_used is None:
            available_plans.append(plan)

    # --------------------------------------------------------
    # همه تست‌ها قبلاً استفاده شده
    # --------------------------------------------------------

    if not available_plans:

        await message.answer(
            "❌ شما تست رایگان تمام سرورها را قبلاً دریافت کرده‌اید."
        )

        return

    # --------------------------------------------------------
    # ساخت کیبورد انتخاب سرور
    # --------------------------------------------------------

    builder = InlineKeyboardBuilder()

    for plan in available_plans:

        title = get_panel_title(plan.panel_key)

        traffic = get_trial_traffic_text(plan)

        button_text = (
            f"{title} | "
            f"{traffic} | "
            f"{plan.duration_days} روز"
        )

        print(
            "TRIAL BUTTON:",
            button_text,
            "callback=",
            f"trial_select:{plan.id}",
        )

        builder.button(
            text=button_text,
            callback_data=f"trial_select:{plan.id}",
        )

    builder.adjust(1)

    # --------------------------------------------------------
    # نمایش انتخاب
    # --------------------------------------------------------

    await message.answer(
        "🎁 <b>سرویس تست رایگان</b>\n\n"
        "هر سرور را فقط یک بار می‌توانید تست کنید.\n\n"
        "👇 لطفاً سرور موردنظر خود را انتخاب کنید:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ============================================================
# 🎯 انتخاب سرور تست
# ============================================================

@router.callback_query()
async def select_trial(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:

    print(
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )
    print(
        "ANY CALLBACK RECEIVED:",
        repr(callback.data),
    )
    print(
        "FROM USER:",
        callback.from_user.id,
    )
    print(
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    )

    await callback.answer("Callback دریافت شد")

    # --------------------------------------------------------
    # استخراج plan_id
    # --------------------------------------------------------

    try:

        raw_plan_id = callback.data.split(":", 1)[1]

        plan_id = int(raw_plan_id)

    except (
        ValueError,
        AttributeError,
        IndexError,
    ):

        print(
            "TRIAL ERROR: INVALID CALLBACK:",
            callback.data,
        )

        await callback.answer(
            "❌ انتخاب نامعتبر است.",
            show_alert=True,
        )

        return

    print(
        "TRIAL SELECTED PLAN ID:",
        plan_id,
    )

    # --------------------------------------------------------
    # گرفتن کاربر
    # --------------------------------------------------------

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    user_id = user.id
    telegram_id = user.telegram_id

    print(
        "TRIAL USER:",
        "id=", user_id,
        "telegram_id=", telegram_id,
    )

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

    print(
        "TRIAL SELECT RESULT:",
        None
        if plan is None
        else {
            "id": plan.id,
            "panel": plan.panel_key,
            "trial": plan.is_trial,
            "active": plan.is_active,
            "name": plan.name,
        }
    )

    # --------------------------------------------------------
    # پلن پیدا نشد
    # --------------------------------------------------------

    if plan is None:

        # برای دیباگ بیشتر، خود plan را بدون فیلتر trial/active می‌خوانیم
        debug_result = await session.execute(
            select(Plan).where(
                Plan.id == plan_id
            )
        )

        debug_plan = debug_result.scalar_one_or_none()

        print(
            "TRIAL DEBUG RAW PLAN:",
            None
            if debug_plan is None
            else {
                "id": debug_plan.id,
                "panel": debug_plan.panel_key,
                "trial": debug_plan.is_trial,
                "active": debug_plan.is_active,
                "name": debug_plan.name,
            }
        )

        await callback.answer(
            "❌ این سرویس تست دیگر در دسترس نیست.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # بررسی اینکه کاربر قبلاً همین پنل را تست کرده
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
        "TRIAL USED CHECK:",
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
    # callback موفق
    # --------------------------------------------------------

    await callback.answer()

    # --------------------------------------------------------
    # حذف دکمه‌ها
    # --------------------------------------------------------

    try:

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

    except Exception as e:

        print(
            "TRIAL EDIT KEYBOARD ERROR:",
            e,
        )

    # --------------------------------------------------------
    # اطلاعات تست
    # --------------------------------------------------------

    traffic = get_trial_traffic_text(plan)

    panel_title = get_panel_title(plan.panel_key)

    await callback.message.answer(
        "⏳ <b>در حال ساخت سرویس تست شما...</b>\n\n"
        f"🌐 <b>سرور:</b> {panel_title}\n"
        f"📦 <b>حجم:</b> {traffic}\n"
        f"⏱ <b>مدت:</b> {plan.duration_days} روز",
        parse_mode="HTML",
    )

    # --------------------------------------------------------
    # نام یکتا برای کلاینت
    #
    # قبلاً:
    # Trial-ir1-926784487
    #
    # اگر یک بار در پنل ساخته شده باشد،
    # دفعه بعد email already in use می‌دهد.
    #
    # بنابراین از order بعداً استفاده می‌کنیم.
    # --------------------------------------------------------

    config_name = (
        f"Trial-{plan.panel_key}-{telegram_id}-{plan.id}"
    )

    # --------------------------------------------------------
    # ساخت Order
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

    await session.flush()

    # ID سفارش را قبل از commit نگه می‌داریم
    order_id = order.id

    print(
        "TRIAL ORDER CREATED:",
        "order_id=", order_id,
        "user_id=", user_id,
        "plan_id=", plan.id,
        "panel=", plan.panel_key,
    )

    # relationshipها را قبل از commit تنظیم می‌کنیم
    order.user = user
    order.plan = plan

    await session.commit()

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

        print(
            "========================================"
        )

        print(
            "TRIAL PROVISION ERROR"
        )

        print(
            "user_id=",
            user_id,
        )

        print(
            "telegram_id=",
            telegram_id,
        )

        print(
            "order_id=",
            order_id,
        )

        print(
            "plan_id=",
            plan.id,
        )

        print(
            "panel=",
            plan.panel_key,
        )

        print(
            "error=",
            repr(e),
        )

        print(
            "========================================"
        )

        await session.rollback()

        await callback.message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        return

    # --------------------------------------------------------
    # ثبت مصرف تست
    #
    # فقط وقتی provision موفق شد.
    # --------------------------------------------------------

    try:

        trial = UserTrial(
            user_id=user_id,
            panel_key=plan.panel_key,
            used=True,
        )

        session.add(trial)

        await session.commit()

        print(
            "TRIAL CREATED:",
            "user_id=", user_id,
            "panel=", plan.panel_key,
            "order_id=", order_id,
        )

    except Exception as e:

        await session.rollback()

        print(
            "TRIAL RECORD ERROR:",
            repr(e),
        )

        # سرویس ساخته شده ولی رکورد تست ثبت نشده.
        # اینجا بهتر است خطا لاگ شود.
        await callback.message.answer(
            "⚠️ سرویس ساخته شد، اما ثبت وضعیت تست با مشکل مواجه شد.\n"
            "لطفاً با پشتیبانی تماس بگیرید."
        )

        return