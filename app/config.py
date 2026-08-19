from pydantic_settings import BaseSettings
from typing import Dict, Optional

class PanelConfig(BaseSettings):
    key: str
    name: str
    url: str
    api_token: str
    inbound_id: int
    protocol: str = "vless"
    api_base_path: str = "/panel/api"
    subscription_url: Optional[str] = None

class Settings(BaseSettings):
    BOT_TOKEN: str
    PANELS: Dict[str, PanelConfig]
    # ... سایر تنظیمات

settings = Settings()