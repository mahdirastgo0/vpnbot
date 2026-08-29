from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def order_review_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تایید",
                    callback_data=f"admin_approve:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ رد",
                    callback_data=f"admin_reject:{order_id}",
                ),
            ]
        ]
    )


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 مدیریت سرویس‌ها",
                    callback_data="admin_manage_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕓 سفارش‌های در انتظار",
                    callback_data="admin_pending_orders",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 ارسال همگانی",
                    callback_data="admin_broadcast",
                )
            ],
        ]
    )


def admin_plans_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ افزودن سرویس",
                    callback_data="admin_add_plan",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ ویرایش سرویس",
                    callback_data="admin_edit_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 فعال / غیرفعال",
                    callback_data="admin_toggle_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 حذف سرویس",
                    callback_data="admin_delete_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 مشاهده همه سرویس‌ها",
                    callback_data="admin_list_all_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 بازگشت",
                    callback_data="admin_back",
                )
            ],
        ]
    )


def admin_plans_list_kb(
    plans,
    prefix: str,
) -> InlineKeyboardMarkup:
    rows = []

    for plan in plans:
        status = "🟢" if plan.is_active else "🔴"

        traffic = (
            "نامحدود"
            if plan.traffic_gb <= 0
            else f"{plan.traffic_gb}GB"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} #{plan.id} | {plan.name} | {traffic} | {plan.price:,}",
                    callback_data=f"{prefix}:{plan.id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بازگشت",
                callback_data="admin_manage_plans",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_plan_edit_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ تغییر نام",
                    callback_data=f"admin_edit_name:{plan_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 تغییر قیمت",
                    callback_data=f"admin_edit_price:{plan_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 تغییر حجم",
                    callback_data=f"admin_edit_traffic:{plan_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 تغییر مدت",
                    callback_data=f"admin_edit_duration:{plan_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 بازگشت",
                    callback_data="admin_edit_plans",
                )
            ],
        ]
    )


def admin_confirm_delete_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ بله، حذف شود",
                    callback_data=f"admin_delete_confirm:{plan_id}",
                ),
                InlineKeyboardButton(
                    text="❌ خیر",
                    callback_data="admin_manage_plans",
                ),
            ]
        ]
    )

def admin_manage_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ افزودن سرویس",
                    callback_data="admin_add_plan",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ ویرایش سرویس",
                    callback_data="admin_edit_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 فعال / غیرفعال",
                    callback_data="admin_toggle_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 حذف سرویس",
                    callback_data="admin_delete_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 مشاهده همه سرویس‌ها",
                    callback_data="admin_list_all_plans",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 بازگشت",
                    callback_data="admin_back",
                )
            ],
        ]
    )   