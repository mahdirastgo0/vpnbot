from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def order_review_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید", callback_data=f"admin_approve:{order_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"admin_reject:{order_id}"),
            ]
        ]
    )


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن پلن", callback_data="admin_add_plan")],
            [InlineKeyboardButton(text="📋 لیست پلن‌ها", callback_data="admin_list_plans")],
            [InlineKeyboardButton(text="🕓 سفارش‌های در انتظار", callback_data="admin_pending_orders")],
        ]
    )
