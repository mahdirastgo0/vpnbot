from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


# ==========================================================
# ENV
# ==========================================================

load_dotenv(".env")
load_dotenv("panel.env", override=False)
load_dotenv("plans.env", override=False)


# ==========================================================
# HELPERS
# ==========================================================

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


def _get_bool(
    key: str,
    default: bool = False,
) -> bool:

    val = os.getenv(key)

    if val is None:
        return default

    return val.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _get_int_list(
    key: str,
) -> list[int]:

    raw = os.getenv(key, "")

    return [
        int(x.strip())
        for x in raw.split(",")
        if x.strip()
    ]


# ==========================================================
# PANEL
# ==========================================================

@dataclass
class PanelConfig:
    key: str
    name: str
    url: str
    api_token: str
    inbound_id: int

    # آدرس واقعی سروری که کاربر باید به آن وصل شود
    # این با URL پنل API فرق دارد.
    server_address: str

    protocol: str = "vless"

    # مسیر API
    api_base_path: str = "/panel/api"

    # ------------------------------------------------------
    # آدرس پایه Subscription (شامل مسیر اختصاصی ساب‌سکریپشن پنل)
    # مثال: https://panel.kenznum.ir:2096/sub/pbakp1v2aolxv0vg
    # این رشته مسیر sub-path رندوم/اختصاصی پنل رو هم باید داشته باشه،
    # چون پنل subLinks واقعی برنمی‌گردونه و باید دستی ساخته بشه.
    # اگه خالی بمونه، کد به یک fallback ناقص (بدون sub-path) می‌افته.
    # ------------------------------------------------------
    subscription_url: str = ""


# ==========================================================
# PLAN
# ==========================================================

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
    description: str = ""


# ==========================================================
# LOAD PANELS
# ==========================================================

def _load_panels() -> dict[str, PanelConfig]:

    raw_keys = os.getenv(
        "PANELS",
        "",
    )

    keys = [
        k.strip()
        for k in raw_keys.split(",")
        if k.strip()
    ]

    panels: dict[str, PanelConfig] = {}

    # ------------------------------------------------------
    # بسیار مهم:
    # PanelConfig باید داخل همین for ساخته شود.
    # ------------------------------------------------------

    for key in keys:

        prefix = f"PANEL_{key}_"

        panels[key] = PanelConfig(
            key=key,

            name=_get(
                prefix + "NAME",
                key,
                required=True,
            ),

            # این فقط آدرس API پنل است
            url=_get(
                prefix + "URL",
                required=True,
            ).rstrip("/"),

            api_token=_get(
                prefix + "API_TOKEN",
                required=True,
            ),

            # اینباندی که کلاینت داخل آن ساخته می‌شود
            inbound_id=int(
                _get(
                    prefix + "INBOUND_ID",
                    required=True,
                )
            ),

            # IP / Domain واقعی اتصال کاربر
            server_address=_get(
                prefix + "SERVER_ADDRESS",
                required=True,
            ),

            protocol=_get(
                prefix + "PROTOCOL",
                "vless",
            ),

            api_base_path=_get(
                prefix + "API_BASE_PATH",
                "/panel/api",
            ).rstrip("/"),

            # اختیاری است، اما برای اینکه لینک Subscription درست ساخته
            # بشه (با مسیر sub-path اختصاصی پنل) شدیداً پیشنهاد می‌شود
            # تنظیم بشه. مثال مقدار:
            # PANEL_<KEY>_SUBSCRIPTION_URL=https://panel.kenznum.ir:2096/sub/pbakp1v2aolxv0vg
            subscription_url=_get(
                prefix + "SUBSCRIPTION_URL",
                "",
            ).rstrip("/"),
        )

    return panels


# ==========================================================
# LOAD PLANS
# ==========================================================

def _load_plans() -> dict[str, PlanConfig]:

    keys = [
        k.strip()
        for k in os.getenv(
            "PLANS",
            "",
        ).split(",")
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

        if plan_type not in (
            "DIRECT",
            "TUNNEL",
        ):
            raise RuntimeError(
                f"نوع پلن «{plan_type}» برای PLAN_{key} نامعتبر است. "
                f"فقط DIRECT یا TUNNEL مجاز است."
            )

        name = _get(
            prefix + "NAME",
            required=True,
        )

        duration_days = int(
            _get(
                prefix + "DAYS",
                required=True,
            )
        )

        traffic_gb = int(
            _get(
                prefix + "TRAFFIC",
                required=True,
            )
        )

        price = int(
            _get(
                prefix + "PRICE",
                required=True,
            )
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


# ==========================================================
# CRYPTO
# ==========================================================

@dataclass
class CryptoWallets:

    usdt_trc20: str
    usdt_bep20: str
    btc: str
    ton: str

    def active_wallets(self) -> dict[str, str]:

        return {
            key: value
            for key, value in self.__dict__.items()
            if value
        }


def _load_crypto_wallets() -> CryptoWallets:

    return CryptoWallets(
        usdt_trc20=_get(
            "CRYPTO_USDT_TRC20_ADDRESS"
        ),

        usdt_bep20=_get(
            "CRYPTO_USDT_BEP20_ADDRESS"
        ),

        btc=_get(
            "CRYPTO_BTC_ADDRESS"
        ),

        ton=_get(
            "CRYPTO_TON_ADDRESS"
        ),
    )


# ==========================================================
# SETTINGS
# ==========================================================

class Settings:

    # ======================================================
    # BOT
    # ======================================================

    BOT_TOKEN: str = _get(
        "BOT_TOKEN",
        required=True,
    )

    ADMIN_IDS: list[int] = _get_int_list(
        "ADMIN_IDS"
    )

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

    # ======================================================
    # DATABASE
    # ======================================================

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
            "postgresql+asyncpg://"
            f"{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}"
            f"/{self.DB_NAME}"
        )

    # ======================================================
    # ZARINPAL
    # ======================================================

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

    # ======================================================
    # CARD TO CARD
    # ======================================================

    CARD_NUMBER: str = _get(
        "CARD_NUMBER"
    )

    CARD_HOLDER_NAME: str = _get(
        "CARD_HOLDER_NAME"
    )

    CARD_BANK_NAME: str = _get(
        "CARD_BANK_NAME"
    )

    # ======================================================
    # CURRENCY
    # ======================================================

    CURRENCY_LABEL: str = _get(
        "CURRENCY_LABEL",
        "تومان",
    )

    # ======================================================
    # RUNTIME
    # ======================================================

    CRYPTO_WALLETS: CryptoWallets
    PANELS: dict[str, PanelConfig]
    PLANS: dict[str, PlanConfig]

    # ======================================================
    # INIT
    # ======================================================

    def __init__(self) -> None:

        self.CRYPTO_WALLETS = (
            _load_crypto_wallets()
        )

        self.PANELS = (
            _load_panels()
        )

        self.PLANS = (
            _load_plans()
        )

        if not self.PANELS:
            raise RuntimeError(
                "حداقل یک پنل باید در PANELS تعریف شده باشد."
            )

        # --------------------------------------------------
        # بررسی پنل‌های پلن
        # --------------------------------------------------

        for plan in self.PLANS.values():

            if plan.panel_key not in self.PANELS:

                raise RuntimeError(
                    f"پلن «{plan.key}» به پنل "
                    f"«{plan.panel_key}» اشاره می‌کند، "
                    f"اما این پنل در PANELS وجود ندارد."
                )


# ==========================================================
# GLOBAL SETTINGS
# ==========================================================

settings = Settings()
