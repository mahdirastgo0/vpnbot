from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def payment_methods_kb(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 کارت به کارت",
                    callback_data=f"pay:card:{plan_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💰 زرین‌پال",
                    callback_data=f"pay:zarinpal:{plan_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🪙 پرداخت با ارز دیجیتال",
                    callback_data=f"pay:crypto:{plan_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ انصراف",
                    callback_data="buy_cancel",
                ),
            ],
        ]
    )


def zarinpal_pay_kb(
    pay_link: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 پرداخت آنلاین",
                    url=pay_link,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data="buy_cancel",
                ),
            ],
        ]
    )