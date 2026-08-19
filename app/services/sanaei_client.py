from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse
import logging

import httpx

from app.config import PanelConfig

logger = logging.getLogger(__name__)


class SanaeiApiError(RuntimeError):
    pass


class SanaeiClient:

    def __init__(self, panel: PanelConfig):
        self.panel = panel

        base_url = panel.url.rstrip("/")

        api_base = getattr(
            panel,
            "api_base_path",
            "/panel/api",
        ).strip("/")

        self.api_base = f"/{api_base}"

        self._client = httpx.AsyncClient(
            base_url=base_url,
            verify=False,
            timeout=30,
            headers={
                "Authorization": f"Bearer {panel.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        if not path.startswith("/"):
            path = "/" + path

        response = await self._client.request(method, path, **kwargs)

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                "پاسخ JSON معتبر نیست.\n"
                f"HTTP: {response.status_code}\n"
                f"URL: {response.url}\n"
                f"Response: {response.text[:1000]}"
            )

        if response.status_code == 401:
            raise SanaeiApiError(f"احراز هویت پنل «{self.panel.name}» رد شد.")
        if response.status_code == 404:
            raise SanaeiApiError(
                "Endpoint پنل پیدا نشد.\n"
                f"URL: {response.url}\n"
                "HTTP: 404"
            )
        if response.status_code >= 400:
            raise SanaeiApiError(
                f"خطای HTTP پنل «{self.panel.name}»:\n"
                f"HTTP: {response.status_code}\n"
                f"{data}"
            )
        if isinstance(data, dict) and data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: {data.get('msg', data)}"
            )

        return data

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:
        inbound_id = inbound_id if inbound_id is not None else self.panel.inbound_id
        if inbound_id is None:
            raise SanaeiApiError("Inbound ID برای این پنل مشخص نشده است.")

        email = (email or "").strip()
        if not email:
            raise SanaeiApiError("نام کانفیگ / email خالی است.")

        client_uuid = str(uuid.uuid4())
        total_bytes = traffic_gb * 1024 * 1024 * 1024 if traffic_gb and traffic_gb > 0 else 0
        expire_ms = int((datetime.now(timezone.utc) + timedelta(days=duration_days)).timestamp() * 1000) if duration_days and duration_days > 0 else 0
        requested_sub_id = uuid.uuid4().hex[:16]

        client_obj = {
            "id": client_uuid,
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": 0,
            "subId": requested_sub_id,
        }

        payload = {"inboundIds": [int(inbound_id)], "client": client_obj}

        # ساخت کلاینت
        data = await self._request("POST", f"{self.api_base}/clients/add", json=payload)

        # دریافت اطلاعات واقعی
        actual_client = await self.get_client(email)
        if not actual_client:
            raise SanaeiApiError("کلاینت ساخته شد اما اطلاعات آن از پنل قابل دریافت نیست.")

        client_info = actual_client.get("client", {})
        actual_uuid = client_info.get("uuid") or client_info.get("id") or actual_client.get("uuid") or actual_client.get("id") or client_uuid
        actual_sub_id = client_info.get("subId") or client_info.get("subID") or client_info.get("sub_id") or actual_client.get("subId") or actual_client.get("subID") or actual_client.get("sub_id")

        if not actual_sub_id:
            raise SanaeiApiError("کلاینت ساخته شد اما subId واقعی از پنل دریافت نشد.")

        logger.info(f"subId دریافت شده از پنل: {actual_sub_id}")

        individual_links = await self.get_client_links(email)

        # نکته: subLinks در این پنل لیستی از کانفیگ‌های تکی (externalLinks)
        # برمی‌گردونه، نه یک لینک ساب کوتاه HTTPS. برای همین اینا رو فقط
        # به individual_links اضافه می‌کنیم (بدون تکراری) و هرگز به‌عنوان
        # subscription_link اصلی استفاده‌شون نمی‌کنیم.
        extra_links = []
        try:
            extra_links = await self.get_subscription_links(actual_sub_id)
        except SanaeiApiError as e:
            logger.warning(f"خطا در دریافت subLinks: {e}")

        for link in extra_links:
            if link not in individual_links:
                individual_links.append(link)

        # لینک ساب همیشه از روی sub-path اختصاصی پنل ساخته می‌شه، نه از پاسخ subLinks
        subscription_link = self.build_subscription_url(actual_sub_id)

        if not subscription_link:
            hostname = self._extract_hostname()
            if hostname:
                subscription_link = f"https://{hostname}:2096/sub/{quote(str(actual_sub_id))}"
                logger.warning(
                    "لینک سابسکریپشن با fallback نهایی (بدون sub-path اختصاصی پنل) ساخته شد: "
                    f"{subscription_link} — برای رفع این مشکل PANEL_{self.panel.key}_SUBSCRIPTION_URL "
                    "را در .env تنظیم کنید."
                )
            else:
                raise SanaeiApiError(
                    f"امکان ساخت لینک Subscription وجود ندارد. subId: {actual_sub_id}, panel.url: {self.panel.url}"
                )

        return {
            "client_uuid": str(actual_uuid),
            "email": email,
            "sub_id": str(actual_sub_id),
            "inbound_id": int(inbound_id),
            "subscription_link": subscription_link,
            "subscription_links": extra_links,
            "individual_links": individual_links,
            "response": data,
            "client": actual_client,
        }

    async def get_client(self, email: str) -> dict | None:
        data = await self._request("GET", f"{self.api_base}/clients/get/{quote(email)}")
        if not isinstance(data, dict):
            return None
        return data.get("obj")

    async def get_client_links(self, email: str) -> list[str]:
        data = await self._request("GET", f"{self.api_base}/clients/links/{quote(email)}")
        if not isinstance(data, dict):
            return []
        obj = data.get("obj")
        if not isinstance(obj, list):
            return []
        links = []
        for item in obj:
            if isinstance(item, str) and item.strip().startswith(("vless://", "vmess://", "trojan://", "ss://", "hy2://", "hysteria://")):
                links.append(item.strip())
        return links

    async def get_subscription_links(self, sub_id: str) -> list[str]:
        """
        نکته مهم: اندپوینت subLinks در این پنل، برخلاف انتظار،
        یک لیست از رشته‌های لینک برنمی‌گردونه؛ یک dict با ساختار
        {"client": {...}, "externalLinks": [...], "inboundIds": [...], "usedTraffic": ...}
        برمی‌گردونه. اینجا هر دو حالت رو پشتیبانی می‌کنیم تا اگه پنل
        یا نسخه‌ی دیگه‌ای فرمت متفاوتی داد، کد کرش نکنه.
        """
        data = await self._request("GET", f"{self.api_base}/clients/subLinks/{quote(str(sub_id))}")
        if not isinstance(data, dict):
            return []

        obj = data.get("obj")

        # حالت قدیمی/فرضی: obj خودش یک لیست از لینک‌هاست
        candidates: list = []
        if isinstance(obj, list):
            candidates = obj
        # حالت واقعی این پنل: obj یک dict هست و لینک‌ها (اگر باشن) زیر externalLinks میان
        elif isinstance(obj, dict):
            external = obj.get("externalLinks")
            if isinstance(external, list):
                candidates = external

        links = []
        for item in candidates:
            if isinstance(item, str) and item.strip().startswith(("vless://", "vmess://", "trojan://", "ss://", "hy2://", "hysteria://")):
                links.append(item.strip())
        return links

    def build_subscription_url(self, sub_id: str) -> str | None:
        subscription_base = getattr(self.panel, "subscription_url", None)
        if subscription_base:
            return f"{subscription_base.rstrip('/')}/{quote(str(sub_id))}"
        hostname = self._extract_hostname()
        if hostname:
            return f"https://{hostname}:2096/sub/{quote(str(sub_id))}"
        return None

    def _extract_hostname(self) -> str | None:
        if not self.panel.url:
            return None
        parsed = urlparse(self.panel.url)
        return parsed.hostname

    async def get_client_traffic(self, email: str) -> dict | None:
        data = await self._request("GET", f"{self.api_base}/clients/traffic/{quote(email)}")
        if isinstance(data, dict):
            return data.get("obj")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        await self._request("POST", f"{self.api_base}/inbounds/{inbound_id}/delClient/{client_uuid}")

    async def close(self) -> None:
        await self._client.aclose()


# Legacy function
def build_config_link(panel: PanelConfig, inbound: dict, client_uuid: str, email: str) -> str:
    # ... (همان کد قبلی)
    pass
