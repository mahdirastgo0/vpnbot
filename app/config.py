from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv(".env")
load_dotenv("panel.env", override=False)
load_dotenv("plans.env", override=False)


def _get(
    key: str,
    default: str | None = None,
    required: bool = False,
) -> str:

    value = os.getenv(key, default)

    if required and not value:
        raise RuntimeError(
            f"متغیر محیطی الزامی «{key}» تنظیم نشده است."
        )

    return value or ""


def _get_bool(
    key: str,
    default: bool = False,
) -> bool:

    value = os.getenv(key)

    if value is None:
        return default

    return value.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


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

    # مثال:
    # https://panel.kenznum.ir:39217/aN1MrpoX46nkjnJyAr
    url: str

    api_token: str

    inbound_id: int

    protocol: str = "vless"

    # مسیر API قابل تنظیم است
    api_base_path: str = "/panel/api"


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


def _load_panels() -> dict[str, PanelConfig]:

    keys = [
        x.strip()
        for x in os.getenv(
            "PANELS",
            "",
        ).split(",")
        if x.strip()
    ]

    panels: dict[str, PanelConfig] = {}

    for key in keys:

        prefix = f"PANEL_{key}_"

        panels[key] = PanelConfig(

            key=key,

            name=_get(
                prefix + "NAME",
                key,
                required=True,
            ),

            url=_get(
                prefix + "URL",
                required=True,
            ).rstrip("/"),

            api_token=_get(
                prefix + "API_TOKEN",
                required=True,
            ),

            inbound_id=int(
                _get(
                    prefix + "INBOUND_ID",
                    required=True,
                )
            ),

            protocol=_get(
                prefix + "PROTOCOL",
                "vless",
            ).lower(),

            api_base_path=_get(
                prefix + "API_BASE_PATH",
                "/panel/api",
            ).rstrip("/"),
        )

    return panels


def _load_plans() -> dict[str, PlanConfig]:

    keys = [
        x.strip()
        for x in os.getenv(
            "PLANS",
            "",
        ).split(",")
        if x.strip()
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
                f"نوع پلن «{plan_type}» نامعتبر است. "
                f"فقط DIRECT یا TUNNEL مجاز است."
            )

        plans[key] = PlanConfig(

            key=key,

            panel_key=panel_key,

            plan_type=plan_type,

            name=_get(
                prefix + "NAME",
                required=True,
            ),

            duration_days=int(
                _get(
                    prefix + "DAYS",
                    required=True,
                )
            ),

            traffic_gb=int(
                _get(
                    prefix + "TRAFFIC",
                    required=True,
                )
            ),

            price=int(
                _get(
                    prefix + "PRICE",
                    required=True,
                )
            ),

            is_active=_get_bool(
                prefix + "ACTIVE",
                True,
            ),

            description=_get(
                prefix + "DESCRIPTION",
                "",
            ),
        )

    return plans


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


class Settings:

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
            f"{self.DB_USER}:"
            f"{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:"
            f"{self.DB_PORT}/"
            f"{self.DB_NAME}"
        )

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

    CARD_NUMBER: str = _get(
        "CARD_NUMBER"
    )

    CARD_HOLDER_NAME: str = _get(
        "CARD_HOLDER_NAME"
    )

    CARD_BANK_NAME: str = _get(
        "CARD_BANK_NAME"
    )

    CURRENCY_LABEL: str = _get(
        "CURRENCY_LABEL",
        "تومان",
    )

    CRYPTO_WALLETS: CryptoWallets
    PANELS: dict[str, PanelConfig]
    PLANS: dict[str, PlanConfig]

    def __init__(self) -> None:

        self.CRYPTO_WALLETS = (
            _load_crypto_wallets()
        )

        self.PANELS = _load_panels()

        self.PLANS = _load_plans()

        if not self.PANELS:

            raise RuntimeError(
                "حداقل یک پنل باید در PANELS تعریف شده باشد."
            )

        for plan in self.PLANS.values():

            if plan.panel_key not in self.PANELS:

                raise RuntimeError(
                    f"پلن «{plan.key}» به پنل "
                    f"«{plan.panel_key}» اشاره می‌کند، "
                    f"اما این پنل وجود ندارد."
                )


settings = Settings()