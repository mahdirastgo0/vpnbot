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

    # ==========================================================
    # REQUEST
    # ==========================================================

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:

        if not path.startswith("/"):
            path = "/" + path

        resp = await self._client.request(
            method,
            path,
            **kwargs,
        )

        try:
            data = resp.json()
        except Exception:

            raise SanaeiApiError(
                f"پاسخ JSON معتبر نیست.\n"
                f"HTTP: {resp.status_code}\n"
                f"URL: {resp.url}\n"
                f"Response: {resp.text[:1000]}"
            )

        if resp.status_code == 401:

            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد."
            )

        if resp.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {resp.url}\n"
                f"HTTP: 404"
            )

        if resp.status_code >= 400:

            raise SanaeiApiError(
                f"خطای HTTP پنل «{self.panel.name}»:\n"
                f"HTTP: {resp.status_code}\n"
                f"{data}"
            )

        if isinstance(data, dict):

            if data.get("success") is False:

                raise SanaeiApiError(
                    f"خطای پنل «{self.panel.name}»: "
                    f"{data.get('msg', data)}"
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

        inbound_id = (
            inbound_id
            or self.panel.inbound_id
        )

        email = (email or "").strip()

        if not email:

            raise SanaeiApiError(
                "نام کانفیگ / email خالی است."
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

        # ------------------------------------------------------
        # طبق API واقعی پنل:
        #
        # /panel/api/clients/add
        #
        # فقط inbound و client را می‌فرستیم.
        # ------------------------------------------------------

        client_obj = {
            "id": client_uuid,
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": 0,
            "subId": sub_id,
        }

        payload = {
            "inboundIds": [
                inbound_id
            ],
            "client": client_obj,
        }

        data = await self._request(
            "POST",
            f"{self.api_base}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # گرفتن Subscription
        # ------------------------------------------------------

        subscription_link = (
            await self.get_subscription_link(
                sub_id
            )
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": sub_id,
            "inbound_id": inbound_id,
            "subscription_link": subscription_link,
            "response": data,
        }

    # ==========================================================
    # SUBSCRIPTION
    # ==========================================================

    async def get_subscription_link(
    self,
    sub_id: str,
) -> str:

    url = (
        f"{self.base_url}"
        f"/clients/subLinks/{sub_id}"
    )

    response = await self.client.get(url)

    if response.status_code == 404:
        raise SanaeiApiError(
            "Endpoint دریافت Subscription در پنل پیدا نشد."
        )

    if response.status_code >= 400:
        raise SanaeiApiError(
            f"خطا در دریافت Subscription "
            f"(HTTP {response.status_code})"
        )

    try:
        data = response.json()
    except Exception:
        raise SanaeiApiError(
            "پاسخ API مربوط به Subscription معتبر نیست."
        )

    def find_link(obj):

        if isinstance(obj, str):
            value = obj.strip()

            if (
                value.startswith("http://")
                or value.startswith("https://")
            ):
                return value

            return None

        if isinstance(obj, dict):

            # کلیدهای احتمالی
            for key in (
                "subscription",
                "subscriptionLink",
                "subscriptionUrl",
                "subLink",
                "subUrl",
                "url",
                "link",
            ):
                value = obj.get(key)

                found = find_link(value)

                if found:
                    return found

            # جستجوی recursive
            for value in obj.values():

                found = find_link(value)

                if found:
                    return found

        elif isinstance(obj, list):

            for item in obj:

                found = find_link(item)

                if found:
                    return found

        return None

    link = find_link(data)

    if not link:
        raise SanaeiApiError(
            "API پنل پاسخ داد اما لینک Subscription "
            "در پاسخ پیدا نشد."
        )

    return link

    # ==========================================================
    # EXTRACT SUB LINK
    # ==========================================================

    @staticmethod
    def _extract_subscription_link(
        data,
    ) -> str | None:

        # ------------------------------------------------------
        # اگر مستقیماً string باشد
        # ------------------------------------------------------

        if isinstance(data, str):

            text = data.strip()

            if (
                text.startswith("http://")
                or text.startswith("https://")
            ):
                return text

        # ------------------------------------------------------
        # اگر list باشد
        # ------------------------------------------------------

        if isinstance(data, list):

            for item in data:

                result = (
                    SanaeiClient
                    ._extract_subscription_link(item)
                )

                if result:
                    return result

        # ------------------------------------------------------
        # اگر dict باشد
        # ------------------------------------------------------

        if isinstance(data, dict):

            # کلیدهای رایج
            possible_keys = (
                "subLink",
                "subUrl",
                "subURL",
                "subscription",
                "subscriptionLink",
                "subscriptionUrl",
                "subscriptionURL",
                "url",
                "link",
                "sub",
            )

            for key in possible_keys:

                value = data.get(key)

                result = (
                    SanaeiClient
                    ._extract_subscription_link(value)
                )

                if result:
                    return result

            # ساختارهایی مثل:
            #
            # {
            #   "obj": {...}
            # }
            #
            # یا:
            #
            # {
            #   "data": {...}
            # }

            for key in (
                "obj",
                "data",
                "result",
                "response",
            ):

                value = data.get(key)

                result = (
                    SanaeiClient
                    ._extract_subscription_link(value)
                )

                if result:
                    return result

            # --------------------------------------------------
            # جستجوی عمیق در تمام مقادیر
            # --------------------------------------------------

            for value in data.values():

                result = (
                    SanaeiClient
                    ._extract_subscription_link(value)
                )

                if result:
                    return result

        return None

    # ==========================================================
    # CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.api_base}/inbounds/getClientTraffics/"
            f"{quote(email)}",
        )

        if isinstance(data, dict):

            return data.get("obj")

        return None

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
            f"{self.api_base}/inbounds/"
            f"{inbound_id}/delClient/"
            f"{client_uuid}",
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self) -> None:

        await self._client.aclose()


# ==============================================================
# LEGACY CONFIG LINK
# ==============================================================

def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    stream_settings = json.loads(
        inbound.get("streamSettings") or "{}"
    )

    network = stream_settings.get(
        "network",
        "tcp",
    )

    security = stream_settings.get(
        "security",
        "none",
    )

    host = (
        panel.url
        .split("://")[-1]
        .split(":")[0]
    )

    port = inbound.get("port")

    remark = quote(
        f"{panel.name}-{email}"
    )

    if panel.protocol == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        if security == "tls":

            params.append(
                "sni=" + host
            )

        if network == "ws":

            path = (
                stream_settings
                .get("wsSettings", {})
                .get("path", "/")
            )

            params.append(
                "path=" + quote(path)
            )

        query = "&".join(params)

        return (
            f"vless://{client_uuid}"
            f"@{host}:{port}"
            f"?{query}"
            f"#{remark}"
        )

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
        "path": (
            stream_settings
            .get("wsSettings", {})
            .get("path", "")
        ),
        "tls": security,
    }

    raw = json.dumps(
        vmess_obj
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )