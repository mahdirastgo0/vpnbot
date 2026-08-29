from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from app.config import settings
from app.database.models import Plan, PlanType


PLAN_TYPE_LABELS = {
    PlanType.DIRECT: "⚡️ مستقیم",
    PlanType.TUNNEL: "🚇 تانل",
}


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 خرید سرویس")],
            [
                KeyboardButton(text="📂 کانفیگ‌های من"),
                KeyboardButton(text="🎧 پشتیبانی"),
            ],
        ],
        resize_keyboard=True,
    )


def panels_kb() -> InlineKeyboardMarkup:
    rows = []

    for key, panel in settings.PANELS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=panel.name,
                    callback_data=f"panel:{key}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb(
    panel_key: str,
    plans: list[Plan],
) -> InlineKeyboardMarkup:

    rows = []

    plans_by_type: dict[PlanType, list[Plan]] = {}

    for plan in plans:
        plans_by_type.setdefault(
            plan.plan_type,
            [],
        ).append(plan)

    for plan_type in (
        PlanType.DIRECT,
        PlanType.TUNNEL,
    ):
        group = plans_by_type.get(plan_type)

        if not group:
            continue

        if len(plans_by_type) > 1:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"── {PLAN_TYPE_LABELS[plan_type]} ──",
                        callback_data="noop",
                    )
                ]
            )

        for plan in group:
            traffic = (
                "نامحدود"
                if plan.traffic_gb <= 0
                else f"{plan.traffic_gb}GB"
            )

            rows.append(
                [
                    InlineKeyboardButton(
                        text=(
                            f"{plan.name} | "
                            f"{plan.duration_days} روز | "
                            f"{traffic} | "
                            f"{plan.price:,} "
                            f"{settings.CURRENCY_LABEL}"
                        ),
                        callback_data=f"plan:{plan.id}",
                    )
                ]
            )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 بازگشت",
                callback_data="back_to_panels",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def payment_methods_kb(
    plan_id: int,
) -> InlineKeyboardMarkup:

    rows = [
        [
            InlineKeyboardButton(
                text="💳 زرین‌پال (غیر فعال)",
                callback_data=f"pay:zarinpal:{plan_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🏦 کارت به کارت",
                callback_data=f"pay:card:{plan_id}",
            )
        ],
    ]

    if settings.CRYPTO_WALLETS.active_wallets():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🪙 رمزارز",
                    callback_data=f"pay:crypto:{plan_id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="❌ لغو",
                callback_data="buy_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def crypto_coins_kb(
    plan_id: int,
) -> InlineKeyboardMarkup:

    labels = {
        "usdt_trc20": "USDT (TRC20)",
        "usdt_bep20": "USDT (BEP20)",
        "btc": "Bitcoin (BTC)",
        "ton": "Toncoin (TON)",
    }

    rows = []

    for coin in settings.CRYPTO_WALLETS.active_wallets():
        rows.append(
            [
                InlineKeyboardButton(
                    text=labels.get(
                        coin,
                        coin.upper(),
                    ),
                    callback_data=(
                        f"crypto_coin:{coin}:{plan_id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="❌ لغو",
                callback_data="buy_cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
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
                )
            ]
        ]
    )


def config_name_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎲 انتخاب اسم تصادفی",
                    callback_data="config_name_random",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data="config_name_cancel",
                )
            ],
        ]
    )


def my_configs_kb(
    configs: list,
) -> InlineKeyboardMarkup:

    rows = []

    for cfg in configs:

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"📱 {cfg.config_name}"
                        f" #{cfg.id}"
                    ),
                    callback_data=(
                        f"show_config:{cfg.id}"
                    ),
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def config_items_kb(
    config_id: int,
    count: int,
) -> InlineKeyboardMarkup:

    rows = []

    for index in range(count):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📱 کانفیگ {index + 1}",
                    callback_data=(
                        f"single_config:{config_id}:{index}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔗 Subscription",
                callback_data=f"show_subscription:{config_id}",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )