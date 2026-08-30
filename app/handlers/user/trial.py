from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    User,
    Plan,
    UserTrial,
    Order,
    OrderStatus,
    PaymentMethod,
)
from app.database.crud import get_or_create_user
from app.services.delivery import provision_and_deliver


router = Router(name="trial")


@router.message(F.text == "🎁 سرویس تست رایگان")
async def get_free_trial(
    message: Message,
    session: AsyncSession,
) -> None:

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # ------------------------------------------------------
    # پیدا کردن تمام پلن‌های تست فعال
    # ------------------------------------------------------

    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_trial.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
    )

    trial_plans = list(result.scalars().all())

    if not trial_plans:
        await message.answer(
            "❌ در حال حاضر هیچ سرویس تست رایگانی در دسترس نیست."
        )
        return

    # ------------------------------------------------------
    # فعلاً اگر چند پنل تست داریم، لیست پنل‌ها را نشان بده
    # ------------------------------------------------------

    available_plans = []

    for plan in trial_plans:

        result = await session.execute(
            select(UserTrial).where(
                UserTrial.user_id == user.id,
                UserTrial.panel_key == plan.panel_key,
                UserTrial.used.is_(True),
            )
        )

        trial = result.scalar_one_or_none()

        if trial:
            await message.answer(
                f"❌ شما قبلاً سرویس تست سرور {plan.panel_key} را دریافت کرده‌اید."
            )
            return

    # ------------------------------------------------------
    # کاربر همه تست‌ها را گرفته
    # ------------------------------------------------------

    if not available_plans:
        await message.answer(
            "❌ شما قبلاً تست رایگان تمام سرورها را دریافت کرده‌اید.\n\n"
            "هر کاربر برای هر سرور فقط یک بار می‌تواند تست بگیرد."
        )
        return

    # ------------------------------------------------------
    # اگر فقط یک پنل تست داریم، مستقیم همان را بده
    # ------------------------------------------------------

    if len(available_plans) == 1:

        plan = available_plans[0]

        await create_trial(
            message=message,
            session=session,
            user=user,
            plan=plan,
        )

        return

    # ------------------------------------------------------
    # چند پنل تست داریم
    # ------------------------------------------------------

    text = (
        "🎁 <b>سرویس‌های تست رایگان</b>\n\n"
        "برای هر سرور یک بار امکان دریافت تست دارید.\n\n"
    )

    for plan in available_plans:

        traffic = (
            f"{plan.traffic_mb} MB"
            if plan.traffic_mb
            else f"{plan.traffic_gb} GB"
        )

        text += (
            f"🌐 <b>{plan.panel_key}</b>\n"
            f"📦 {traffic}\n"
            f"⏳ {plan.duration_days} روز\n\n"
        )

    # ------------------------------------------------------
    # فعلاً انتخاب خودکار اولین تست موجود
    # ------------------------------------------------------

    plan = available_plans[0]

    await create_trial(
        message=message,
        session=session,
        user=user,
        plan=plan,
    )


async def create_trial(
    message: Message,
    session: AsyncSession,
    user: User,
    plan: Plan,
) -> None:

    # ------------------------------------------------------
    # بررسی دوباره برای جلوگیری از درخواست همزمان
    # ------------------------------------------------------

    result = await session.execute(
        select(UserTrial)
        .where(
            UserTrial.user_id == user.id,
            UserTrial.panel_key == plan.panel_key,
            UserTrial.used.is_(True),
        )
    )

    if result.scalar_one_or_none() is not None:
        await message.answer(
            "❌ شما قبلاً تست این سرور را دریافت کرده‌اید."
        )
        return

    # ------------------------------------------------------
    # ساخت رکورد Trial
    # ------------------------------------------------------

    trial = UserTrial(
        user_id=user.id,
        panel_key=plan.panel_key,
        used=True,
    )

    session.add(trial)

    await session.commit()

    # ------------------------------------------------------
    # ساخت سفارش رایگان
    # ------------------------------------------------------

    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        amount=0,
        payment_method=PaymentMethod.TRIAL,
        status=OrderStatus.PAID,
        config_name=f"Trial-{plan.panel_key}-{message.from_user.id}",
    )

    session.add(order)

    await session.commit()

    await session.refresh(order)

    # relationshipهای لازم
    order.plan = plan
    order.user = user

    # ------------------------------------------------------
    # ساخت کانفیگ
    # ------------------------------------------------------

    try:

        await provision_and_deliver(
            bot=message.bot,
            session=session,
            order=order,
        )

        # --------------------------------------------------
        # فقط بعد از موفقیت ساخت کانفیگ، تست مصرف شود
        # --------------------------------------------------

        trial.used = True

        await session.commit()

    except Exception as e:

        await session.rollback()

        await message.answer(
            "❌ متأسفانه ساخت سرویس تست انجام نشد.\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید."
        )

        print(f"TRIAL PROVISION ERROR: {e}")