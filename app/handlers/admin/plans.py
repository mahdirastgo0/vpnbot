from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import list_active_plans
from app.database.models import Plan, PlanType
from app.keyboards.user_kb import PLAN_TYPE_LABELS
from app.middlewares.admin_filter import IsAdmin
from app.states.user_states import AdminPlanFlow

router = Router(name="admin_plans")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _panels_choice_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=p.name, callback_data=f"admin_panel_choice:{key}")]
        for key, p in settings.PANELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_type_choice_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin_type_choice:{pt.value}")]
        for pt, label in PLAN_TYPE_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("addplan"))
async def add_plan_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminPlanFlow.waiting_panel)
    await message.answer("پلن برای کدوم پنل باشه؟", reply_markup=_panels_choice_kb())


@router.callback_query(AdminPlanFlow.waiting_panel, F.data.startswith("admin_panel_choice:"))
async def add_plan_panel(callback: CallbackQuery, state: FSMContext) -> None:
    panel_key = callback.data.split(":", 1)[1]
    await state.update_data(panel_key=panel_key)
    await state.set_state(AdminPlanFlow.waiting_type)
    await callback.message.answer(
        "این پلن مستقیمه یا از طریق تانل؟ (تانل معمولاً پایدارتره و منطقیه گرون‌تر/محدودتر باشه)",
        reply_markup=_plan_type_choice_kb(),
    )
    await callback.answer()


@router.callback_query(AdminPlanFlow.waiting_type, F.data.startswith("admin_type_choice:"))
async def add_plan_type(callback: CallbackQuery, state: FSMContext) -> None:
    plan_type = callback.data.split(":", 1)[1]
    await state.update_data(plan_type=plan_type)
    await state.set_state(AdminPlanFlow.waiting_name)
    await callback.message.answer("نام پلن رو بفرست (مثلاً «۱ ماهه ۵۰ گیگ»):")
    await callback.answer()


@router.message(AdminPlanFlow.waiting_name, F.text)
async def add_plan_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminPlanFlow.waiting_duration)
    await message.answer("مدت اعتبار پلن به روز چند باشه؟ (فقط عدد)")


@router.message(AdminPlanFlow.waiting_duration, F.text)
async def add_plan_duration(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("لطفاً فقط عدد بفرست.")
        return
    await state.update_data(duration_days=int(message.text.strip()))
    await state.set_state(AdminPlanFlow.waiting_traffic)
    await message.answer("حجم پلن به گیگابایت چند باشه؟ (فقط عدد، ۰ برای نامحدود)")


@router.message(AdminPlanFlow.waiting_traffic, F.text)
async def add_plan_traffic(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("لطفاً فقط عدد بفرست.")
        return
    await state.update_data(traffic_gb=int(message.text.strip()))
    await state.set_state(AdminPlanFlow.waiting_price)
    await message.answer(f"قیمت پلن به {settings.CURRENCY_LABEL} چند باشه؟ (فقط عدد)")


@router.message(AdminPlanFlow.waiting_price, F.text)
async def add_plan_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.text.strip().isdigit():
        await message.answer("لطفاً فقط عدد بفرست.")
        return

    data = await state.get_data()
    plan = Plan(
        panel_key=data["panel_key"],
        plan_type=PlanType(data["plan_type"]),
        name=data["name"],
        duration_days=data["duration_days"],
        traffic_gb=data["traffic_gb"],
        price=int(message.text.strip()),
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ پلن «{plan.name}» ({PLAN_TYPE_LABELS[plan.plan_type]}) با موفقیت اضافه شد."
    )


@router.message(Command("plans"))
async def list_plans(message: Message, session: AsyncSession) -> None:
    plans = await list_active_plans(session)
    if not plans:
        await message.answer(
            "هیچ پلنی ثبت نشده. پلن‌ها توی فایل .env تعریف نمی‌شن — با /addplan یا اسکریپت "
            "seed_plans.py اضافه‌شون کن."
        )
        return

    text = "📋 لیست پلن‌های فعال:\n\n"
    grouped: dict[str, list[Plan]] = {}
    for p in plans:
        grouped.setdefault(p.panel_key, []).append(p)

    for panel_key, plan_list in grouped.items():
        panel = settings.PANELS.get(panel_key)
        text += f"🌍 {panel.name if panel else panel_key}\n"
        for p in plan_list:
            text += (
                f"  #{p.id} | {PLAN_TYPE_LABELS[p.plan_type]} | {p.name} | "
                f"{p.duration_days} روز | {p.traffic_gb} گیگ | {p.price:,} {settings.CURRENCY_LABEL}\n"
            )
        text += "\n"
    await message.answer(text)


@router.message(Command("delplan"))
async def del_plan(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("استفاده: /delplan <شماره پلن>")
        return
    plan = await session.get(Plan, int(parts[1]))
    if plan is None:
        await message.answer("پلن پیدا نشد.")
        return
    plan.is_active = False
    await session.commit()
    await message.answer(f"پلن #{plan.id} غیرفعال شد.")
