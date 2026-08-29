from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import (
    create_plan,
    get_plan,
    list_all_plans,
    list_active_plans,
    update_plan,
)
from app.database.models import PlanType
from app.keyboards.admin_kb import (
    admin_confirm_delete_kb,
    admin_manage_plans_kb,
    admin_plan_edit_kb,
    admin_plans_list_kb,
)
from app.keyboards.user_kb import PLAN_TYPE_LABELS
from app.middlewares.admin_filter import IsAdmin
from app.states.user_states import AdminPlanFlow


router = Router(name="admin_plans")

router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ==========================================================
# HELPERS
# ==========================================================

def panels_kb() -> InlineKeyboardMarkup:
    rows = []

    for key, panel in settings.PANELS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=panel.name,
                    callback_data=f"admin_panel_choice:{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="❌ لغو",
                callback_data="admin_manage_plans",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ مستقیم",
                    callback_data="admin_type_choice:direct",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚇 تانل",
                    callback_data="admin_type_choice:tunnel",
                )
            ],
        ]
    )


# ==========================================================
# MENU
# ==========================================================

@router.callback_query(F.data == "admin_manage_plans")
async def manage_plans(
    callback: CallbackQuery,
) -> None:
    await callback.message.edit_text(
        "📦 مدیریت سرویس‌ها\n\n"
        "عملیات مورد نظر را انتخاب کنید:",
        reply_markup=admin_manage_plans_kb(),
    )
    await callback.answer()


# ==========================================================
# ADD PLAN
# ==========================================================

@router.callback_query(F.data == "admin_add_plan")
async def add_plan_start_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(AdminPlanFlow.waiting_panel)

    await callback.message.edit_text(
        "➕ افزودن سرویس\n\n"
        "سرویس برای کدام سرور باشد؟",
        reply_markup=panels_kb(),
    )

    await callback.answer()


@router.message(Command("addplan"))
async def add_plan_start_command(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(AdminPlanFlow.waiting_panel)

    await message.answer(
        "➕ افزودن سرویس\n\n"
        "سرویس برای کدام سرور باشد؟",
        reply_markup=panels_kb(),
    )


@router.callback_query(
    AdminPlanFlow.waiting_panel,
    F.data.startswith("admin_panel_choice:"),
)
async def add_plan_panel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    panel_key = callback.data.split(":", 1)[1]

    if panel_key not in settings.PANELS:
        await callback.answer(
            "❌ سرور پیدا نشد.",
            show_alert=True,
        )
        return

    await state.update_data(panel_key=panel_key)
    await state.set_state(AdminPlanFlow.waiting_type)

    await callback.message.edit_text(
        "نوع سرویس را انتخاب کنید:",
        reply_markup=plan_type_kb(),
    )

    await callback.answer()


@router.callback_query(
    AdminPlanFlow.waiting_type,
    F.data.startswith("admin_type_choice:"),
)
async def add_plan_type(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    plan_type = callback.data.split(":", 1)[1]

    if plan_type not in ("direct", "tunnel"):
        await callback.answer(
            "❌ نوع سرویس نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(plan_type=plan_type)
    await state.set_state(AdminPlanFlow.waiting_name)

    await callback.message.edit_text(
        "📝 نام سرویس را وارد کنید:\n\n"
        "مثلاً:\n"
        "۱ ماهه ۱۰ گیگ"
    )

    await callback.answer()


@router.message(
    AdminPlanFlow.waiting_name,
    F.text,
)
async def add_plan_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = message.text.strip()

    if not name:
        await message.answer("❌ نام سرویس نمی‌تواند خالی باشد.")
        return

    if len(name) > 128:
        await message.answer(
            "❌ نام سرویس حداکثر ۱۲۸ کاراکتر باشد."
        )
        return

    await state.update_data(name=name)
    await state.set_state(AdminPlanFlow.waiting_duration)

    await message.answer(
        "📅 مدت سرویس را به روز وارد کنید:\n\n"
        "مثلاً: 30"
    )


@router.message(
    AdminPlanFlow.waiting_duration,
    F.text,
)
async def add_plan_duration(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if not value.isdigit() or int(value) <= 0:
        await message.answer(
            "❌ لطفاً یک عدد صحیح بزرگ‌تر از صفر وارد کنید."
        )
        return

    await state.update_data(duration_days=int(value))
    await state.set_state(AdminPlanFlow.waiting_traffic)

    await message.answer(
        "📊 حجم سرویس را به گیگابایت وارد کنید:\n\n"
        "مثلاً: 10\n\n"
        "برای نامحدود عدد 0 را وارد کنید."
    )


@router.message(
    AdminPlanFlow.waiting_traffic,
    F.text,
)
async def add_plan_traffic(
    message: Message,
    state: FSMContext,
) -> None:
    value = message.text.strip()

    if not value.isdigit():
        await message.answer("❌ فقط عدد وارد کنید.")
        return

    traffic = int(value)

    if traffic < 0:
        await message.answer("❌ حجم نامعتبر است.")
        return

    await state.update_data(traffic_gb=traffic)
    await state.set_state(AdminPlanFlow.waiting_price)

    await message.answer(
        f"💰 قیمت سرویس را به {settings.CURRENCY_LABEL} وارد کنید:\n\n"
        "مثلاً: 120000"
    )


@router.message(
    AdminPlanFlow.waiting_price,
    F.text,
)
async def add_plan_price(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = message.text.strip()

    if not value.isdigit():
        await message.answer("❌ فقط عدد وارد کنید.")
        return

    price = int(value)

    if price <= 0:
        await message.answer(
            "❌ قیمت باید بیشتر از صفر باشد."
        )
        return

    data = await state.get_data()

    plan = await create_plan(
        session=session,
        panel_key=data["panel_key"],
        plan_type=PlanType(data["plan_type"]),
        name=data["name"],
        duration_days=data["duration_days"],
        traffic_gb=data["traffic_gb"],
        price=price,
        is_active=True,
    )

    await state.clear()

    traffic = (
        "نامحدود"
        if plan.traffic_gb <= 0
        else f"{plan.traffic_gb} گیگ"
    )

    panel = settings.PANELS.get(plan.panel_key)

    await message.answer(
        "✅ سرویس با موفقیت اضافه شد.\n\n"
        f"🆔 شناسه: #{plan.id}\n"
        f"📦 نام: {plan.name}\n"
        f"🖥 سرور: {panel.name if panel else plan.panel_key}\n"
        f"📊 حجم: {traffic}\n"
        f"📅 مدت: {plan.duration_days} روز\n"
        f"💰 قیمت: {plan.price:,} {settings.CURRENCY_LABEL}",
        reply_markup=admin_manage_plans_kb(),
    )


# ==========================================================
# LIST ALL
# ==========================================================

@router.callback_query(F.data == "admin_list_all_plans")
async def list_all_plans_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plans = await list_all_plans(session)

    if not plans:
        await callback.message.edit_text(
            "📋 هنوز هیچ سرویسی ثبت نشده.",
            reply_markup=admin_manage_plans_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📋 همه سرویس‌ها:\n\n"
        "🟢 = فعال\n"
        "🔴 = غیرفعال",
        reply_markup=admin_plans_list_kb(
            plans,
            "admin_plan_view",
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_plan_view:")
)
async def view_plan(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(
            "❌ شناسه نامعتبر.",
            show_alert=True,
        )
        return

    plan = await get_plan(session, plan_id)

    if plan is None:
        await callback.answer(
            "❌ سرویس پیدا نشد.",
            show_alert=True,
        )
        return

    panel = settings.PANELS.get(plan.panel_key)

    traffic = (
        "♾ نامحدود"
        if plan.traffic_gb <= 0
        else f"{plan.traffic_gb} گیگ"
    )

    status = "🟢 فعال" if plan.is_active else "🔴 غیرفعال"

    await callback.message.edit_text(
        f"📦 سرویس #{plan.id}\n\n"
        f"نام: {plan.name}\n"
        f"سرور: {panel.name if panel else plan.panel_key}\n"
        f"نوع: {PLAN_TYPE_LABELS.get(plan.plan_type, str(plan.plan_type))}\n"
        f"حجم: {traffic}\n"
        f"مدت: {plan.duration_days} روز\n"
        f"قیمت: {plan.price:,} {settings.CURRENCY_LABEL}\n"
        f"وضعیت: {status}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ ویرایش",
                        callback_data=f"admin_edit_plan:{plan.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 تغییر وضعیت",
                        callback_data=f"admin_toggle:{plan.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 حذف",
                        callback_data=f"admin_delete:{plan.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 بازگشت",
                        callback_data="admin_list_all_plans",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ==========================================================
# EDIT PLAN
# ==========================================================

@router.callback_query(F.data == "admin_edit_plans")
async def edit_plans_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plans = await list_all_plans(session)

    if not plans:
        await callback.message.edit_text(
            "❌ هیچ سرویسی وجود ندارد.",
            reply_markup=admin_manage_plans_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "✏️ سرویس مورد نظر برای ویرایش را انتخاب کنید:",
        reply_markup=admin_plans_list_kb(
            plans,
            "admin_edit_plan",
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_edit_plan:")
)
async def edit_plan_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    plan = await get_plan(session, plan_id)

    if plan is None:
        await callback.answer(
            "❌ سرویس پیدا نشد.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        f"✏️ ویرایش سرویس #{plan.id}\n\n"
        f"📦 {plan.name}\n"
        f"💰 {plan.price:,} {settings.CURRENCY_LABEL}\n\n"
        "چه چیزی را می‌خواهید تغییر دهید؟",
        reply_markup=admin_plan_edit_kb(plan.id),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_edit_name:")
)
async def edit_name_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(AdminPlanFlow.waiting_edit_name)

    await callback.message.edit_text(
        "📝 نام جدید سرویس را وارد کنید:"
    )

    await callback.answer()


@router.message(
    AdminPlanFlow.waiting_edit_name,
    F.text,
)
async def edit_name_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    name = message.text.strip()

    if not name:
        await message.answer("❌ نام نمی‌تواند خالی باشد.")
        return

    if len(name) > 128:
        await message.answer(
            "❌ نام حداکثر ۱۲۸ کاراکتر باشد."
        )
        return

    data = await state.get_data()
    plan = await get_plan(session, int(data["plan_id"]))

    if plan is None:
        await state.clear()
        await message.answer("❌ سرویس پیدا نشد.")
        return

    await update_plan(
        session,
        plan,
        name=name,
    )

    await state.clear()

    await message.answer(
        f"✅ نام سرویس به «{name}» تغییر کرد.",
        reply_markup=admin_manage_plans_kb(),
    )


@router.callback_query(
    F.data.startswith("admin_edit_price:")
)
async def edit_price_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(AdminPlanFlow.waiting_edit_price)

    await callback.message.edit_text(
        f"💰 قیمت جدید سرویس #{plan_id} را وارد کنید:"
    )

    await callback.answer()


@router.message(
    AdminPlanFlow.waiting_edit_price,
    F.text,
)
async def edit_price_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = message.text.strip()

    if not value.isdigit() or int(value) <= 0:
        await message.answer(
            "❌ قیمت باید یک عدد بزرگ‌تر از صفر باشد."
        )
        return

    data = await state.get_data()
    plan = await get_plan(session, int(data["plan_id"]))

    if plan is None:
        await state.clear()
        await message.answer("❌ سرویس پیدا نشد.")
        return

    await update_plan(
        session,
        plan,
        price=int(value),
    )

    await state.clear()

    await message.answer(
        f"✅ قیمت سرویس #{plan.id} تغییر کرد.\n\n"
        f"💰 قیمت جدید: {plan.price:,} {settings.CURRENCY_LABEL}",
        reply_markup=admin_manage_plans_kb(),
    )


@router.callback_query(
    F.data.startswith("admin_edit_traffic:")
)
async def edit_traffic_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(AdminPlanFlow.waiting_edit_traffic)

    await callback.message.edit_text(
        "📊 حجم جدید را به گیگابایت وارد کنید.\n\n"
        "برای نامحدود: 0"
    )

    await callback.answer()


@router.message(
    AdminPlanFlow.waiting_edit_traffic,
    F.text,
)
async def edit_traffic_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = message.text.strip()

    if not value.isdigit():
        await message.answer("❌ فقط عدد وارد کنید.")
        return

    data = await state.get_data()
    plan = await get_plan(session, int(data["plan_id"]))

    if plan is None:
        await state.clear()
        await message.answer("❌ سرویس پیدا نشد.")
        return

    await update_plan(
        session,
        plan,
        traffic_gb=int(value),
    )

    await state.clear()

    traffic = (
        "نامحدود"
        if plan.traffic_gb <= 0
        else f"{plan.traffic_gb} گیگ"
    )

    await message.answer(
        f"✅ حجم سرویس #{plan.id} تغییر کرد.\n\n"
        f"📊 حجم جدید: {traffic}",
        reply_markup=admin_manage_plans_kb(),
    )


@router.callback_query(
    F.data.startswith("admin_edit_duration:")
)
async def edit_duration_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(AdminPlanFlow.waiting_edit_duration)

    await callback.message.edit_text(
        "📅 مدت جدید سرویس را به روز وارد کنید:"
    )

    await callback.answer()


@router.message(
    AdminPlanFlow.waiting_edit_duration,
    F.text,
)
async def edit_duration_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    value = message.text.strip()

    if not value.isdigit() or int(value) <= 0:
        await message.answer(
            "❌ مدت باید یک عدد بزرگ‌تر از صفر باشد."
        )
        return

    data = await state.get_data()
    plan = await get_plan(session, int(data["plan_id"]))

    if plan is None:
        await state.clear()
        await message.answer("❌ سرویس پیدا نشد.")
        return

    await update_plan(
        session,
        plan,
        duration_days=int(value),
    )

    await state.clear()

    await message.answer(
        f"✅ مدت سرویس #{plan.id} تغییر کرد.\n\n"
        f"📅 مدت جدید: {plan.duration_days} روز",
        reply_markup=admin_manage_plans_kb(),
    )


# ==========================================================
# TOGGLE
# ==========================================================

@router.callback_query(F.data == "admin_toggle_plans")
async def toggle_plans_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plans = await list_all_plans(session)

    if not plans:
        await callback.message.edit_text(
            "❌ هیچ سرویسی وجود ندارد.",
            reply_markup=admin_manage_plans_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🔄 سرویس مورد نظر را انتخاب کنید:",
        reply_markup=admin_plans_list_kb(
            plans,
            "admin_toggle",
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_toggle:")
)
async def toggle_plan(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    plan = await get_plan(session, plan_id)

    if plan is None:
        await callback.answer(
            "❌ سرویس پیدا نشد.",
            show_alert=True,
        )
        return

    plan.is_active = not plan.is_active
    await session.commit()

    status = "فعال 🟢" if plan.is_active else "غیرفعال 🔴"

    await callback.message.edit_text(
        f"✅ وضعیت سرویس #{plan.id} تغییر کرد.\n\n"
        f"📦 {plan.name}\n"
        f"وضعیت جدید: {status}",
        reply_markup=admin_manage_plans_kb(),
    )

    await callback.answer()


# ==========================================================
# DELETE
# ==========================================================

@router.callback_query(F.data == "admin_delete_plans")
async def delete_plans_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plans = await list_all_plans(session)

    if not plans:
        await callback.message.edit_text(
            "❌ هیچ سرویسی وجود ندارد.",
            reply_markup=admin_manage_plans_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🗑 سرویس مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=admin_plans_list_kb(
            plans,
            "admin_delete",
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_delete:")
)
async def delete_plan_start(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    plan = await get_plan(session, plan_id)

    if plan is None:
        await callback.answer(
            "❌ سرویس پیدا نشد.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        f"⚠️ حذف سرویس\n\n"
        f"🆔 #{plan.id}\n"
        f"📦 {plan.name}\n"
        f"💰 {plan.price:,} {settings.CURRENCY_LABEL}\n\n"
        "آیا مطمئن هستید؟",
        reply_markup=admin_confirm_delete_kb(plan.id),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_delete_confirm:")
)
async def delete_plan_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    plan_id = int(callback.data.split(":", 1)[1])

    plan = await get_plan(session, plan_id)

    if plan is None:
        await callback.answer(
            "❌ سرویس پیدا نشد.",
            show_alert=True,
        )
        return

    # عملاً حذف فیزیکی نمی‌کنیم؛
    # سرویس را غیرفعال می‌کنیم تا سفارش‌های قدیمی
    # همچنان به plan_id خود دسترسی داشته باشند.
    plan.is_active = False
    await session.commit()

    await callback.message.edit_text(
        f"🗑 سرویس #{plan.id} غیرفعال شد.\n\n"
        "سرویس دیگر به کاربران نمایش داده نمی‌شود.",
        reply_markup=admin_manage_plans_kb(),
    )

    await callback.answer()


# ==========================================================
# OLD COMMANDS
# ==========================================================

@router.message(Command("plans"))
async def list_plans_command(
    message: Message,
    session: AsyncSession,
) -> None:
    plans = await list_all_plans(session)

    if not plans:
        await message.answer("❌ هیچ سرویسی ثبت نشده.")
        return

    text = "📋 همه سرویس‌ها:\n\n"

    for p in plans:
        status = "🟢" if p.is_active else "🔴"

        traffic = (
            "نامحدود"
            if p.traffic_gb <= 0
            else f"{p.traffic_gb} گیگ"
        )

        panel = settings.PANELS.get(p.panel_key)

        text += (
            f"{status} #{p.id}\n"
            f"📦 {p.name}\n"
            f"🖥 {panel.name if panel else p.panel_key}\n"
            f"📊 {traffic}\n"
            f"📅 {p.duration_days} روز\n"
            f"💰 {p.price:,} {settings.CURRENCY_LABEL}\n\n"
        )

    await message.answer(text)


@router.message(Command("delplan"))
async def delete_plan_command(
    message: Message,
    session: AsyncSession,
) -> None:
    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "استفاده:\n"
            "/delplan <شماره پلن>"
        )
        return

    plan = await get_plan(
        session,
        int(parts[1]),
    )

    if plan is None:
        await message.answer("❌ سرویس پیدا نشد.")
        return

    plan.is_active = False
    await session.commit()

    await message.answer(
        f"✅ سرویس #{plan.id} غیرفعال شد."
    )