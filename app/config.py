from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(
    key: str,
    default: str | None = None,
    required: bool = False,
) -> str:
    val = os.getenv(key, default)

    if required and not val:
        raise RuntimeError(
            f"متغیر محیطی الزامی «{key}» در فایل .env تنظیم نشده است."
        )

    return val or ""


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)

    if val is None:
        return default

    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int_list(key: str) -> list[int]:
    raw = os.getenv(key, "")

    return [
        int(x.strip())
        for x in raw.split(",")
        if x.strip()
    ]


@dataclass
class PanelConfig:
    key: str
    name: str
    url: str
    api_token: str
    inbound_id: int
    protocol: str = "vless"


@dataclass
class PlanConfig:
    """
    اطلاعات یک پلن که مستقیماً از .env خوانده می‌شود.
    """

    key: str
    panel_key: str
    plan_type: str
    name: str
    duration_days: int
    traffic_gb: int
    price: int
    is_active: bool = True
    description: str = ""


def _load_panels() -> dict[str, PanelConfig]:
    keys = [
        k.strip()
        for k in os.getenv("PANELS", "").split(",")
        if k.strip()
    ]

    panels: dict[str, PanelConfig] = {}

    for key in keys:
        prefix = f"PANEL_{key}_"

        panels[key] = PanelConfig(
            key=key,
            name=_get(prefix + "NAME", key, required=True),
            url=_get(prefix + "URL", required=True).rstrip("/"),
            api_token=_get(prefix + "API_TOKEN", required=True),
            inbound_id=int(
                _get(prefix + "INBOUND_ID", required=True)
            ),
            protocol=_get(prefix + "PROTOCOL", "vless"),
        )

    return panels


def _load_plans() -> dict[str, PlanConfig]:
    """
    تمام پلن‌ها را از .env می‌خواند.

    مثال:

    PLANS=pol25,pol50

    PLAN_pol25_PANEL=pol
    PLAN_pol25_TYPE=DIRECT
    PLAN_pol25_NAME=...
    PLAN_pol25_DAYS=30
    PLAN_pol25_TRAFFIC=25
    PLAN_pol25_PRICE=60000
    PLAN_pol25_ACTIVE=true
    """

    keys = [
        k.strip()
        for k in os.getenv("PLANS", "").split(",")
        if k.strip()
    ]

    plans: dict[str, PlanConfig] = {}

    for key in keys:
        prefix = f"PLAN_{key}_"

        panel_key = _get(
            prefix + "PANEL",
            required=True,
        )

        plan_type = _get(
            prefix + "TYPE",
            required=True,
        ).strip().upper()

        if plan_type not in ("DIRECT", "TUNNEL"):
            raise RuntimeError(
                f"نوع پلن «{plan_type}» برای PLAN_{key} نامعتبر است. "
                f"فقط DIRECT یا TUNNEL مجاز است."
            )

        name = _get(
            prefix + "NAME",
            required=True,
        )

        duration_days = int(
            _get(prefix + "DAYS", required=True)
        )

        traffic_gb = int(
            _get(prefix + "TRAFFIC", required=True)
        )

        price = int(
            _get(prefix + "PRICE", required=True)
        )

        is_active = _get_bool(
            prefix + "ACTIVE",
            True,
        )

        description = _get(
            prefix + "DESCRIPTION",
            "",
        )

        plans[key] = PlanConfig(
            key=key,
            panel_key=panel_key,
            plan_type=plan_type,
            name=name,
            duration_days=duration_days,
            traffic_gb=traffic_gb,
            price=price,
            is_active=is_active,
            description=description,
        )

    return plans


@dataclass
class CryptoWallets:
    usdt_trc20: str
    usdt_bep20: str
    btc: str
    ton: str

    def active_wallets(self) -> dict[str, str]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v
        }


def _load_crypto_wallets() -> CryptoWallets:
    return CryptoWallets(
        usdt_trc20=_get("CRYPTO_USDT_TRC20_ADDRESS"),
        usdt_bep20=_get("CRYPTO_USDT_BEP20_ADDRESS"),
        btc=_get("CRYPTO_BTC_ADDRESS"),
        ton=_get("CRYPTO_TON_ADDRESS"),
    )


class Settings:

    # ==========================================================
    # BOT
    # ==========================================================

    BOT_TOKEN: str = _get(
        "BOT_TOKEN",
        required=True,
    )

    ADMIN_IDS: list[int] = _get_int_list("ADMIN_IDS")

    SUPPORT_USERNAME: str = _get(
        "SUPPORT_USERNAME",
        "@support",
    )

    FORCE_JOIN_CHANNEL_ID: str = _get(
        "FORCE_JOIN_CHANNEL_ID"
    )

    FORCE_JOIN_CHANNEL_USERNAME: str = _get(
        "FORCE_JOIN_CHANNEL_USERNAME"
    )

    # ==========================================================
    # DATABASE
    # ==========================================================

    DB_HOST: str = _get(
        "DB_HOST",
        "localhost",
    )

    DB_PORT: str = _get(
        "DB_PORT",
        "5432",
    )

    DB_NAME: str = _get(
        "DB_NAME",
        required=True,
    )

    DB_USER: str = _get(
        "DB_USER",
        required=True,
    )

    DB_PASSWORD: str = _get(
        "DB_PASSWORD",
        required=True,
    )

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ==========================================================
    # ZARINPAL
    # ==========================================================

    ZARINPAL_MERCHANT_ID: str = _get(
        "ZARINPAL_MERCHANT_ID",
        required=True,
    )

    ZARINPAL_SANDBOX: bool = _get_bool(
        "ZARINPAL_SANDBOX",
        True,
    )

    ZARINPAL_CALLBACK_BASE_URL: str = _get(
        "ZARINPAL_CALLBACK_BASE_URL",
        "http://127.0.0.1:8080",
    )

    CALLBACK_SERVER_HOST: str = _get(
        "CALLBACK_SERVER_HOST",
        "0.0.0.0",
    )

    CALLBACK_SERVER_PORT: int = int(
        _get(
            "CALLBACK_SERVER_PORT",
            "8080",
        )
    )

    # ==========================================================
    # CARD TO CARD
    # ==========================================================

    CARD_NUMBER: str = _get("CARD_NUMBER")

    CARD_HOLDER_NAME: str = _get(
        "CARD_HOLDER_NAME"
    )

    CARD_BANK_NAME: str = _get(
        "CARD_BANK_NAME"
    )

    # ==========================================================
    # CURRENCY
    # ==========================================================

    CURRENCY_LABEL: str = _get(
        "CURRENCY_LABEL",
        "تومان",
    )

    # ==========================================================
    # CRYPTO / PANELS / PLANS
    # ==========================================================

    CRYPTO_WALLETS: CryptoWallets
    PANELS: dict[str, PanelConfig]
    PLANS: dict[str, PlanConfig]

    def __init__(self) -> None:

        self.CRYPTO_WALLETS = _load_crypto_wallets()

        self.PANELS = _load_panels()

        self.PLANS = _load_plans()

        if not self.PANELS:
            raise RuntimeError(
                "حداقل یک پنل باید در PANELS تعریف شده باشد."
            )

        # بررسی اینکه پلن به پنل موجود اشاره کند
        for plan in self.PLANS.values():

            if plan.panel_key not in self.PANELS:
                raise RuntimeError(
                    f"پلن «{plan.key}» به پنل "
                    f"«{plan.panel_key}» اشاره می‌کند، "
                    f"اما این پنل در PANELS وجود ندارد."
                )


settings = Settings()