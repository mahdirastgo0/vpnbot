from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import list_active_plans
from app.keyboards.user_kb import PLAN_TYPE_LABELS, panels_kb, payment_methods_kb, plans_kb
from app.utils import texts

router = Router(name="buy")


@router.message(F.text == "🛒 خرید سرویس")
async def choose_panel(message: Message) -> None:
    await message.answer(texts.CHOOSE_PANEL, reply_markup=panels_kb())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    # دکمه‌ی سربرگ گروه‌بندی پلن‌ها - فقط برای نمایشه، کاری انجام نمی‌ده
    await callback.answer()


@router.callback_query(F.data.startswith("panel:"))
async def show_plans(callback: CallbackQuery, session: AsyncSession) -> None:
    panel_key = callback.data.split(":", 1)[1]
    plans = await list_active_plans(session, panel_key=panel_key)
    if not plans:
        await callback.answer(texts.NO_PLANS, show_alert=True)
        return
    await callback.message.edit_text(texts.CHOOSE_PLAN, reply_markup=plans_kb(panel_key, plans))
    await callback.answer()


@router.callback_query(F.data == "back_to_panels")
async def back_to_panels(callback: CallbackQuery) -> None:
    await callback.message.edit_text(texts.CHOOSE_PANEL, reply_markup=panels_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("plan:"))
async def choose_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    plan_id = int(callback.data.split(":", 1)[1])
    from app.database.crud import get_plan

    plan = await get_plan(session, plan_id)
    if plan is None or not plan.is_active:
        await callback.answer("این پلن دیگر موجود نیست.", show_alert=True)
        return

    panel = settings.PANELS[plan.panel_key]
    summary = texts.ORDER_SUMMARY.format(
        panel_name=panel.name,
        plan_type=PLAN_TYPE_LABELS[plan.plan_type],
        plan_name=plan.name,
        duration=plan.duration_days,
        traffic=plan.traffic_gb,
        amount=plan.price,
        currency=settings.CURRENCY_LABEL,
    )
    await callback.message.edit_text(
        summary + "\n" + texts.CHOOSE_PAYMENT,
        reply_markup=payment_methods_kb(plan.id),
    )
    await callback.answer()
