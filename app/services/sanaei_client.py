from __future__ import annotations

import asyncio
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


class SanaeiTimeoutError(SanaeiApiError):
    pass


class SanaeiClient:

    def __init__(self, panel: PanelConfig):
        self.panel = panel
        base_url = panel.url.rstrip("/")
        api_base = getattr(panel, "api_base_path", "/panel/api").strip("/")
        self.api_base = f"/{api_base}"

        self._client = httpx.AsyncClient(
            base_url=base_url,
            verify=False,
            timeout=httpx.Timeout(60, connect=10),
            headers={
                "Authorization": f"Bearer {panel.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        if not path.startswith("/"):
            path = "/" + path

        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.ConnectTimeout as e:
            raise SanaeiTimeoutError(
                f"اتصال به پنل «{self.panel.name}» برقرار نشد (ConnectTimeout)."
            ) from e
        except httpx.TimeoutException as e:
            raise SanaeiTimeoutError(
                f"پنل «{self.panel.name}» پاسخ نداد ({type(e).__name__})."
            ) from e
        except httpx.HTTPError as e:
            raise SanaeiApiError(
                f"خطای ارتباط با پنل: {type(e).__name__}: {e}"
            ) from e

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
            raise SanaeiApiError(f"Endpoint پیدا نشد (404).\nURL: {response.url}")
        if response.status_code >= 400:
            raise SanaeiApiError(
                f"HTTP {response.status_code}:\n{data}"
            )
        if isinstance(data, dict) and data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل: {data.get('msg', data)}"
            )

        return data

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
        traffic_mb: int | None = None,
    ) -> dict:

        inbound_id = inbound_id if inbound_id is not None else self.panel.inbound_id
        if inbound_id is None:
            raise SanaeiApiError("Inbound ID مشخص نشده است.")

        email = (email or "").strip()
        if not email:
            raise SanaeiApiError("email خالی است.")

        client_uuid = str(uuid.uuid4())

        if traffic_mb is not None and traffic_mb > 0:
            total_bytes = traffic_mb * 1024 * 1024
        elif traffic_gb and traffic_gb > 0:
            total_bytes = traffic_gb * 1024 * 1024 * 1024
        else:
            total_bytes = 0

        expire_ms = (
            int((datetime.now(timezone.utc) + timedelta(days=duration_days)).timestamp() * 1000)
            if duration_days and duration_days > 0
            else 0
        )

        requested_sub_id = uuid.uuid4().hex[:16]

        # ============ payload استاندارد 3x-ui ============
        client_entry = {
            "id": client_uuid,
            "flow": "",
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": requested_sub_id,
            "reset": 0,
        }

        settings_json = json.dumps(
            {"clients": [client_entry]},
            ensure_ascii=False,
        )

        payload = {
            "id": int(inbound_id),
            "settings": settings_json,
        }

        # ============ POST /inbounds/addClient ============
        await self._request(
            "POST",
            f"{self.api_base}/inbounds/addClient",
            json=payload,
        )

        # ============ اطلاعات واقعی ============
        actual_client = await self.get_client(email)
        if not actual_client:
            raise SanaeiApiError("کلاینت ساخته شد اما اطلاعات دریافت نشد.")

        client_info = actual_client.get("client", {}) or actual_client
        actual_uuid = client_info.get("id") or client_info.get("uuid") or client_uuid
        actual_sub_id = (
            client_info.get("subId")
            or client_info.get("sub_id")
            or requested_sub_id
        )

        logger.info(f"client ساخته شد | email={email} | subId={actual_sub_id}")

        subscription_link = self.build_subscription_url(actual_sub_id)
        if not subscription_link:
            hostname = self._extract_hostname()
            if hostname:
                subscription_link = f"https://{hostname}:2096/sub/{quote(str(actual_sub_id))}"
            else:
                raise SanaeiApiError("امکان ساخت لینک Subscription نیست.")

        return {
            "client_uuid": str(actual_uuid),
            "email": email,
            "sub_id": str(actual_sub_id),
            "inbound_id": int(inbound_id),
            "subscription_link": subscription_link,
            "subscription_links": [],
            "individual_links": [],
            "response": {},
            "client": actual_client,
        }

    async def get_client(self, email: str) -> dict | None:
        inbound_id = self.panel.inbound_id
        if not inbound_id:
            return None

        data = await self._request(
            "GET",
            f"{self.api_base}/inbounds/get/{inbound_id}",
        )

        obj = data.get("obj") or {}

        for stat in (obj.get("clientStats") or []):
            if stat.get("email") == email:
                return {
                    "client": {
                        "id": stat.get("id") or stat.get("uuid"),
                        "email": email,
                        "subId": stat.get("subId"),
                    }
                }

        settings_raw = obj.get("settings")
        if settings_raw:
            try:
                settings = json.loads(settings_raw)
                for c in settings.get("clients", []):
                    if c.get("email") == email:
                        return {"client": c}
            except Exception as e:
                logger.warning(f"parse settings failed: {e}")

        return None

    async def get_client_links(self, email: str) -> list[str]:
        return []

    async def get_subscription_links(self, sub_id: str) -> list[str]:
        return []

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
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        await self._request(
            "POST",
            f"{self.api_base}/inbounds/{inbound_id}/delClient/{client_uuid}",
        )

    async def close(self) -> None:
        await self._client.aclose()


def build_config_link(panel: PanelConfig, inbound: dict, client_uuid: str, email: str) -> str:
    return ""