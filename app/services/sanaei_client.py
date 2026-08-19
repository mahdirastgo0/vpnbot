from __future__ import annotations

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
            headers={
                "Authorization": f"Bearer {panel.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    # ==========================================================
    # REQUEST
    # ==========================================================

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:

        resp = await self._client.request(
            method,
            path,
            **kwargs,
        )

        try:
            data = resp.json()
        except Exception:

            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {resp.status_code})"
            )

        if resp.status_code == 401:

            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد."
            )

        if resp.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {self.panel.url}{path}\n"
                f"HTTP: 404"
            )

        if resp.status_code >= 400:

            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', data)}"
            )

        if not data.get("success", True):

            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', 'خطای نامشخص')}"
            )

        return data

    # ==========================================================
    # ADD CLIENT
    # ==========================================================

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:

        email = (email or "").strip()

        if not email:

            raise SanaeiApiError(
                "نام کانفیگ / email خالی است."
            )

        inbound_id = (
            inbound_id
            or self.panel.inbound_id
        )

        client_uuid = str(
            uuid.uuid4()
        )

        sub_id = uuid.uuid4().hex[:16]

        expire_ms = int(
            (
                datetime.now(timezone.utc)
                + timedelta(days=duration_days)
            ).timestamp()
            * 1000
        )

        total_bytes = (
            traffic_gb
            * 1024
            * 1024
            * 1024
            if traffic_gb > 0
            else 0
        )

        client_obj = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "limitIp": 0,
            "tgId": 0,
            "subId": sub_id,
            "flow": "",
            "reset": 0,
        }

        payload = {
            "inboundIds": [
                inbound_id
            ],
            "client": client_obj,
        }

        await self._request(
            "POST",
            f"{self.panel.api_base_path}/clients/add",
            json=payload,
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": sub_id,
            "inbound_id": inbound_id,
        }

    # ==========================================================
    # GET SUB LINKS
    # ==========================================================

    async def get_subscription_link(
        self,
        sub_id: str,
    ) -> str:

        if not sub_id:

            raise SanaeiApiError(
                "subId کلاینت خالی است."
            )

        path = (
            f"{self.panel.api_base_path}"
            f"/clients/subLinks/{quote(sub_id)}"
        )

        resp = await self._client.get(path)

        try:
            data = resp.json()
        except Exception:

            raise SanaeiApiError(
                f"پاسخ subLinks قابل خواندن نیست.\n"
                f"HTTP: {resp.status_code}\n"
                f"BODY: {resp.text[:2000]}"
            )

        if resp.status_code == 401:

            raise SanaeiApiError(
                "احراز هویت API پنل برای subLinks رد شد."
            )

        if resp.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint subLinks پیدا نشد.\n"
                f"URL: {self.panel.url}{path}"
            )

        if resp.status_code >= 400:

            raise SanaeiApiError(
                f"خطای subLinks پنل.\n"
                f"HTTP: {resp.status_code}\n"
                f"Response: {data}"
            )

        # ======================================================
        # استخراج لینک از هر ساختار ممکن
        # ======================================================

        def find_url(value):

            # ------------------------------
            # string
            # ------------------------------

            if isinstance(value, str):

                value = value.strip()

                if value.startswith(
                    (
                        "http://",
                        "https://",
                        "vless://",
                        "vmess://",
                        "trojan://",
                        "ss://",
                    )
                ):
                    return value

                return None

            # ------------------------------
            # dict
            # ------------------------------

            if isinstance(value, dict):

                # اول کلیدهای محتمل
                preferred_keys = (
                    "url",
                    "link",
                    "subLink",
                    "subUrl",
                    "subscription",
                    "subscriptionLink",
                    "subscriptionUrl",
                    "sub",
                    "sub_url",
                    "sub_link",
                )

                for key in preferred_keys:

                    if key in value:

                        result = find_url(
                            value[key]
                        )

                        if result:
                            return result

                # بعد تمام مقادیر
                for item in value.values():

                    result = find_url(item)

                    if result:
                        return result

                return None

            # ------------------------------
            # list
            # ------------------------------

            if isinstance(value, list):

                for item in value:

                    result = find_url(item)

                    if result:
                        return result

                return None

            return None

        link = find_url(data)

        if link:

            return link

        # ======================================================
        # لینک پیدا نشد
        #
        # پاسخ واقعی را در خطا نمایش می‌دهیم تا دقیقاً بفهمیم
        # API پنل شما چه چیزی برمی‌گرداند.
        # ======================================================

        import json

        pretty = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )

        raise SanaeiApiError(
            "API پنل subLinks پاسخ داد اما لینک پیدا نشد.\n\n"
            "پاسخ واقعی پنل:\n"
            f"{pretty[:5000]}"
        )

    # ==========================================================
    # TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}"
            f"/inbounds/getClientTraffics/"
            f"{quote(email)}",
        )

        return data.get("obj")

    # ==========================================================
    # DELETE CLIENT
    # ==========================================================

    async def delete_client(
        self,
        inbound_id: int,
        client_uuid: str,
    ) -> None:

        await self._request(
            "POST",
            f"{self.panel.api_base_path}"
            f"/inbounds/{inbound_id}"
            f"/delClient/{client_uuid}",
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self) -> None:

        await self._client.aclose()