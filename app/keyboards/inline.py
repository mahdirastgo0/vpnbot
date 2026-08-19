from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback_data import ConfigListCallback


def config_list_keyboard(configs: list) -> InlineKeyboardMarkup:
    """ساخت کیبورد برای نمایش لیست کانفیگ‌ها"""
    builder = InlineKeyboardBuilder()
    
    for config in configs:
        # استفاده از config_name برای نمایش
        label = config.config_name or f"کانفیگ #{config.id}"
        builder.button(
            text=label,
            callback_data=ConfigListCallback(config_id=config.id).pack()
        )
    
    builder.adjust(1)  # هر دکمه در یک ردیف
    builder.row(
        InlineKeyboardButton(
            text="🔙 بازگشت به منو",
            callback_data="back_to_menu"
        )
    )
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بازگشت به منو"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔙 بازگشت به منو",
        callback_data="back_to_menu"
    )
    return builder.as_markup()