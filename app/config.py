from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("panel.env", override=True)
load_dotenv("plans.env", override=False)


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
    key: str
    panel_key: str
    plan_type: str
    name: str
    duration_days: int
    traffic_gb: int
    price: int
    is_active: bool


def _load_plans() -> dict[str, PlanConfig]:
    """
    پلن‌ها از فایل plans.env خوانده می‌شوند.
    """

    plans: dict[str, PlanConfig] = {}

    if not os.path.exists("plans.env"):
        raise RuntimeError(
            "فایل plans.env پیدا نشد."
        )

    plan_env: dict[str, str] = {}

    with open("plans.env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            plan_env[key.strip()] = value.strip()

    keys = [
        k.strip()
        for k in plan_env.get("PLANS", "").split(",")
        if k.strip()
    ]

    if not keys:
        raise RuntimeError(
            "هیچ پلنی در plans.env تعریف نشده است."
        )

    for key in keys:
        prefix = f"PLAN_{key}_"

        panel_key = plan_env.get(prefix + "PANEL", "").strip()

        if not panel_key:
            raise RuntimeError(
                f"{prefix}PANEL در plans.env تنظیم نشده است."
            )

        plan_type = plan_env.get(prefix + "TYPE", "").strip().upper()

        if plan_type not in ("DIRECT", "TUNNEL"):
            raise RuntimeError(
                f"نوع پلن {key} نامعتبر است: {plan_type}. "
                f"فقط DIRECT یا TUNNEL مجاز است."
            )

        name = plan_env.get(prefix + "NAME", "").strip()

        if not name:
            raise RuntimeError(
                f"{prefix}NAME در plans.env تنظیم نشده است."
            )

        duration_days = int(
            plan_env[prefix + "DAYS"]
        )

        traffic_gb = int(
            plan_env[prefix + "TRAFFIC"]
        )

        price = int(
            plan_env[prefix + "PRICE"]
        )

        active_raw = plan_env.get(
            prefix + "ACTIVE",
            "true"
        )

        is_active = active_raw.lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        description = plan_env.get(
            prefix + "DESCRIPTION",
            "",
        ).strip()

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

    PLANS: list[PlanConfig]

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