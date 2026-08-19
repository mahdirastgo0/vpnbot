from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

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
            [KeyboardButton(text="📂 کانفیگ‌های من"), KeyboardButton(text="🎧 پشتیبانی")],
        ],
        resize_keyboard=True,
    )


def panels_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=panel.name, callback_data=f"panel:{key}")]
        for key, panel in settings.PANELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb(panel_key: str, plans: list[Plan]) -> InlineKeyboardMarkup:
    """
    پلن‌ها را زیر یک سربرگ برای هر نوع (مستقیم / تانل) گروه‌بندی می‌کند تا کاربر
    راحت‌تر فرق قیمت و حجم هرکدوم رو ببینه.
    """
    rows: list[list[InlineKeyboardButton]] = []
    plans_by_type: dict[PlanType, list[Plan]] = {}
    for p in plans:
        plans_by_type.setdefault(p.plan_type, []).append(p)

    # ترتیب نمایش: مستقیم اول، بعد تانل
    for plan_type in (PlanType.DIRECT, PlanType.TUNNEL):
        group = plans_by_type.get(plan_type)
        if not group:
            continue
        if len(plans_by_type) > 1:
            rows.append([InlineKeyboardButton(text=f"── {PLAN_TYPE_LABELS[plan_type]} ──", callback_data="noop")])
        for p in group:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{p.name} | {p.duration_days} روز | {p.traffic_gb} گیگ | {p.price:,} {settings.CURRENCY_LABEL}",
                        callback_data=f"plan:{p.id}",
                    )
                ]
            )

    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_panels")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_methods_kb(plan_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💳 زرین‌پال (آنلاین)", callback_data=f"pay:zarinpal:{plan_id}")],
        [InlineKeyboardButton(text="🏦 کارت به کارت", callback_data=f"pay:card:{plan_id}")],
    ]
    if settings.CRYPTO_WALLETS.active_wallets():
        rows.append([InlineKeyboardButton(text="🪙 رمزارز", callback_data=f"pay:crypto:{plan_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crypto_coins_kb(plan_id: int) -> InlineKeyboardMarkup:
    labels = {
        "usdt_trc20": "USDT (TRC20)",
        "usdt_bep20": "USDT (BEP20)",
        "btc": "Bitcoin (BTC)",
        "ton": "Toncoin (TON)",
    }
    rows = [
        [InlineKeyboardButton(text=labels[coin], callback_data=f"crypto_coin:{coin}:{plan_id}")]
        for coin in settings.CRYPTO_WALLETS.active_wallets()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def zarinpal_pay_kb(pay_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 پرداخت آنلاین", url=pay_link)]]
    )


def my_configs_kb(configs: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📱 دریافت QR و لینک #{cfg.id}", callback_data=f"show_config:{cfg.id}")]
        for cfg in configs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
