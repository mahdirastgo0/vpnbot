from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import get_plan
from app.keyboards.payment_kb import payment_methods_kb
from app.keyboards.user_kb import config_name_kb
from app.states.buy import BuyFlow
from app.utils import texts


router = Router(name="user_buy")


PLAN_TYPE_LABELS = {
    "DIRECT": "مستقیم",
    "TUNNEL": "تانل",
}


# ============================================================
# انتخاب پلن
# ============================================================

@router.callback_query(F.data.startswith("buy:"))
async def select_plan(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(
            "پلن نامعتبر است.",
            show_alert=True,
        )
        return

    plan = await get_plan(session, plan_id)

    if plan is None or not plan.is_active:
        await callback.answer(
            "این پلن دیگر موجود نیست.",
            show_alert=True,
        )
        return

    await state.update_data(
        plan_id=plan.id,
    )

    await state.set_state(
        BuyFlow.waiting_config_name
    )

    await callback.message.edit_text(
        texts.CONFIG_NAME_REQUEST,
        reply_markup=config_name_kb(),
    )

    await callback.answer()


# ============================================================
# دریافت نام کانفیگ
# ============================================================

@router.message(
    BuyFlow.waiting_config_name,
    F.text,
)
async def receive_config_name(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:

    name = message.text.strip()

    if not name:
        await message.answer(
            "❌ اسم کانفیگ نمی‌تواند خالی باشد."
        )
        return

    if len(name) > 128:
        await message.answer(
            "❌ اسم کانفیگ حداکثر ۱۲۸ کاراکتر باشد."
        )
        return

    data = await state.get_data()
    plan_id = data.get("plan_id")

    if not plan_id:
        await state.clear()

        await message.answer(
            "❌ سفارش پیدا نشد.\n"
            "لطفاً دوباره از خرید سرویس شروع کن."
        )
        return

    plan = await get_plan(
        session,
        int(plan_id),
    )

    if plan is None or not plan.is_active:
        await state.clear()

        await message.answer(
            "❌ این پلن دیگر موجود نیست."
        )
        return

    await state.update_data(
        config_name=name,
    )

    panel = settings.PANELS.get(
        plan.panel_key
    )

    if panel is None:
        await state.clear()

        await message.answer(
            "❌ پنل این پلن پیدا نشد."
        )
        return

    plan_type = PLAN_TYPE_LABELS.get(
        plan.plan_type,
        plan.plan_type,
    )

    summary = texts.ORDER_SUMMARY.format(
        panel_name=panel.name,
        plan_type=plan_type,
        plan_name=plan.name,
        duration=plan.duration_days,
        traffic=(
            "نامحدود"
            if plan.traffic_gb <= 0
            else plan.traffic_gb
        ),
        amount=plan.price,
        currency=settings.CURRENCY_LABEL,
    )

    await message.answer(
        summary + "\n\n" + texts.CHOOSE_PAYMENT,
        reply_markup=payment_methods_kb(plan.id),
    )


# ============================================================
# دکمه لغو وارد کردن نام
# ============================================================

@router.callback_query(
    BuyFlow.waiting_config_name,
    F.data == "buy_cancel",
)
async def cancel_config_name(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.clear()

    await callback.message.edit_text(
        "❌ خرید لغو شد."
    )

    await callback.answer()