"""
تمام تنظیمات ربات از فایل .env خوانده می‌شود.
هیچ مقدار حساس (توکن، رمز پنل، شماره کارت و ...) نباید داخل کد نوشته شود.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"متغیر محیطی الزامی «{key}» در فایل .env تنظیم نشده است.")
    return val or ""


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int_list(key: str) -> list[int]:
    raw = os.getenv(key, "")
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


@dataclass
class PanelConfig:
    key: str
    name: str
    url: str
    api_token: str
    inbound_id: int
    protocol: str = "vless"


def _load_panels() -> dict[str, PanelConfig]:
    keys = [k.strip() for k in os.getenv("PANELS", "").split(",") if k.strip()]
    panels: dict[str, PanelConfig] = {}
    for key in keys:
        prefix = f"PANEL_{key}_"
        panels[key] = PanelConfig(
            key=key,
            name=_get(prefix + "NAME", key, required=True),
            url=_get(prefix + "URL", required=True).rstrip("/"),
            api_token=_get(prefix + "API_TOKEN", required=True),
            inbound_id=int(_get(prefix + "INBOUND_ID", required=True)),
            protocol=_get(prefix + "PROTOCOL", "vless"),
        )
    return panels


@dataclass
class CryptoWallets:
    usdt_trc20: str
    usdt_bep20: str
    btc: str
    ton: str

    def active_wallets(self) -> dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v}


def _load_crypto_wallets() -> CryptoWallets:
    return CryptoWallets(
        usdt_trc20=_get("CRYPTO_USDT_TRC20_ADDRESS"),
        usdt_bep20=_get("CRYPTO_USDT_BEP20_ADDRESS"),
        btc=_get("CRYPTO_BTC_ADDRESS"),
        ton=_get("CRYPTO_TON_ADDRESS"),
    )


class Settings:
    # --- ربات ---
    BOT_TOKEN: str = _get("BOT_TOKEN", required=True)
    ADMIN_IDS: list[int] = _get_int_list("ADMIN_IDS")
    SUPPORT_USERNAME: str = _get("SUPPORT_USERNAME", "@support")
    FORCE_JOIN_CHANNEL_ID: str = _get("FORCE_JOIN_CHANNEL_ID")
    FORCE_JOIN_CHANNEL_USERNAME: str = _get("FORCE_JOIN_CHANNEL_USERNAME")

    # --- دیتابیس ---
    DB_HOST: str = _get("DB_HOST", "localhost")
    DB_PORT: str = _get("DB_PORT", "5432")
    DB_NAME: str = _get("DB_NAME", required=True)
    DB_USER: str = _get("DB_USER", required=True)
    DB_PASSWORD: str = _get("DB_PASSWORD", required=True)

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # --- زرین‌پال ---
    ZARINPAL_MERCHANT_ID: str = _get("ZARINPAL_MERCHANT_ID", required=True)
    ZARINPAL_SANDBOX: bool = _get_bool("ZARINPAL_SANDBOX", True)
    ZARINPAL_CALLBACK_BASE_URL: str = _get("ZARINPAL_CALLBACK_BASE_URL", "http://127.0.0.1:8080")
    CALLBACK_SERVER_HOST: str = _get("CALLBACK_SERVER_HOST", "0.0.0.0")
    CALLBACK_SERVER_PORT: int = int(_get("CALLBACK_SERVER_PORT", "8080"))

    # --- کارت به کارت ---
    CARD_NUMBER: str = _get("CARD_NUMBER")
    CARD_HOLDER_NAME: str = _get("CARD_HOLDER_NAME")
    CARD_BANK_NAME: str = _get("CARD_BANK_NAME")

    # --- واحد پول ---
    CURRENCY_LABEL: str = _get("CURRENCY_LABEL", "تومان")

    # --- رمزارز و پنل‌ها (در __init__ مقداردهی می‌شوند) ---
    CRYPTO_WALLETS: CryptoWallets
    PANELS: dict[str, PanelConfig]

    def __init__(self) -> None:
        self.CRYPTO_WALLETS = _load_crypto_wallets()
        self.PANELS = _load_panels()
        if not self.PANELS:
            raise RuntimeError("حداقل یک پنل باید در PANELS تعریف شده باشد.")


settings = Settings()
