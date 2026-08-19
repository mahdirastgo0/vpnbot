"""
کلاینت غیرهمزمان برای API پنل 3x-ui (معروف به «سنایی»).
احراز هویت با یک API Token ثابت انجام می‌شود (هدر Authorization: Bearer <token>) —
دیگر نیازی به لاگین با یوزرنیم/پسورد و مدیریت سشن نیست.
هر پنل تعریف‌شده در .env یک نمونه جدا از این کلاس می‌گیرد.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from app.config import PanelConfig


class SanaeiApiError(RuntimeError):
    pass


class SanaeiClient:
    def __init__(self, panel: PanelConfig):
        self.panel = panel
        self._client = httpx.AsyncClient(
            base_url=panel.url,
            verify=False,
            timeout=20,
            headers={"Authorization": f"Bearer {panel.api_token}"},
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code == 401:
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد. API Token را در .env بررسی کن."
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise SanaeiApiError(f"خطای پنل «{self.panel.name}»: {data.get('msg')}")
        return data

    async def list_inbounds(self) -> list[dict]:
        data = await self._request("GET", "/panel/api/inbounds/list")
        return data.get("obj", [])

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:
        """
        یک کاربر جدید روی اینباند مشخص‌شده می‌سازد و اطلاعات لازم برای ساخت لینک کانفیگ را برمی‌گرداند.
        """
        inbound_id = inbound_id or self.panel.inbound_id
        client_uuid = str(uuid.uuid4())
        expire_ms = int((datetime.now(timezone.utc) + timedelta(days=duration_days)).timestamp() * 1000)
        total_bytes = traffic_gb * 1024 * 1024 * 1024 if traffic_gb > 0 else 0

        client_obj = {
            "id": client_uuid,
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": uuid.uuid4().hex[:16],
        }
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_obj]}),
        }
        await self._request("POST", "/panel/api/inbounds/addClient", json=payload)

        # جزئیات اینباند را برای ساخت لینک کانفیگ می‌گیریم
        inbounds = await self.list_inbounds()
        inbound = next((i for i in inbounds if i["id"] == inbound_id), None)
        if inbound is None:
            raise SanaeiApiError("اینباند مورد نظر روی پنل پیدا نشد.")

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound": inbound,
        }

    async def get_client_traffic(self, email: str) -> dict | None:
        data = await self._request("GET", f"/panel/api/inbounds/getClientTraffics/{quote(email)}")
        return data.get("obj")

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        await self._request("POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}")

    async def close(self) -> None:
        await self._client.aclose()


def build_config_link(panel: PanelConfig, inbound: dict, client_uuid: str, email: str) -> str:
    """
    از روی اطلاعات اینباند و کلاینت، لینک vless:// یا vmess:// می‌سازد.
    توجه: بسته به نسخه‌ی پنل و تنظیمات استریم (تی‌ال‌اس/ریالیتی/وب‌سوکت و ...) ممکن است
    لازم باشد این تابع را متناسب با تنظیمات خودتان تنظیم کنید.
    """
    stream_settings = json.loads(inbound.get("streamSettings") or "{}")
    network = stream_settings.get("network", "tcp")
    security = stream_settings.get("security", "none")
    host = panel.url.split("://")[-1].split(":")[0]
    port = inbound.get("port")
    remark = quote(f"{panel.name}-{email}")

    if panel.protocol == "vless":
        params = [f"type={network}", f"security={security}"]
        if security == "tls":
            params.append("sni=" + host)
        if network == "ws":
            path = stream_settings.get("wsSettings", {}).get("path", "/")
            params.append("path=" + quote(path))
        query = "&".join(params)
        return f"vless://{client_uuid}@{host}:{port}?{query}#{remark}"

    # پیش‌فرض: vmess (base64 json طبق استاندارد v2rayN)
    import base64

    vmess_obj = {
        "v": "2",
        "ps": f"{panel.name}-{email}",
        "add": host,
        "port": port,
        "id": client_uuid,
        "aid": "0",
        "net": network,
        "type": "none",
        "host": "",
        "path": stream_settings.get("wsSettings", {}).get("path", ""),
        "tls": security,
    }
    raw = json.dumps(vmess_obj).encode()
    return "vmess://" + base64.b64encode(raw).decode()
