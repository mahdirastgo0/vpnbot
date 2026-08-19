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

        self.base_url = panel.url.rstrip("/")

        api_base_path = getattr(
            panel,
            "api_base_path",
            "/panel/api",
        )

        api_base_path = api_base_path.strip("/")
        self.api_base = f"/{api_base_path}"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
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
    ):
        if not path.startswith("/"):
            path = "/" + path

        response = await self.client.request(
            method,
            path,
            **kwargs,
        )

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
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد."
            )

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

        # ------------------------------------------------------
        # Inbound
        # ------------------------------------------------------

        if inbound_id is None:
            inbound_id = getattr(
                self.panel,
                "inbound_id",
                None,
            )

        if inbound_id is None:
            raise SanaeiApiError(
                f"Inbound ID برای پنل «{self.panel.name}» مشخص نشده است."
            )

        try:
            inbound_id = int(inbound_id)
        except (TypeError, ValueError):
            raise SanaeiApiError(
                f"Inbound ID نامعتبر است: {inbound_id}"
            )

        # ------------------------------------------------------
        # Email
        # ------------------------------------------------------

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "client email خالی است."
            )

        # ------------------------------------------------------
        # UUID
        # ------------------------------------------------------

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # Expiry
        # ------------------------------------------------------

        if duration_days > 0:
            expire_at = (
                datetime.now(timezone.utc)
                + timedelta(days=duration_days)
            )

            expiry_ms = int(
                expire_at.timestamp() * 1000
            )
        else:
            expiry_ms = 0

        # ------------------------------------------------------
        # Traffic
        #
        # پنل totalGB را به صورت byte می‌گیرد.
        # ------------------------------------------------------

        if traffic_gb > 0:
            total_bytes = (
                int(traffic_gb)
                * 1024
                * 1024
                * 1024
            )
        else:
            total_bytes = 0

        # ======================================================
        # Payload واقعی clients/add
        #
        # inboundIds بیرون client است.
        # tgId حتماً integer است.
        # subId را خودمان جعل نمی‌کنیم؛
        # پنل باید آن را بسازد.
        # ======================================================

        client_obj = {
            "id": client_uuid,
            "email": email,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "tgId": 0,
            "limitIp": 0,
            "enable": True,
        }

        payload = {
            "client": client_obj,
            "inboundIds": [
                inbound_id
            ],
        }

        # ------------------------------------------------------
        # Create
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            f"{self.api_base}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # بعضی نسخه‌های پنل در پاسخ clients/add
        # خود Client را برنمی‌گردانند.
        #
        # بنابراین بعد از ساخت، Client را با email
        # دوباره از پنل می‌خوانیم.
        # ------------------------------------------------------

        client_data = await self.get_client(
            email
        )

        if not client_data:
            raise SanaeiApiError(
                "کلاینت روی پنل ساخته شد، "
                "اما اطلاعات کلاینت از API دریافت نشد."
            )

        # ------------------------------------------------------
        # UUID واقعی
        # ------------------------------------------------------

        real_uuid = (
            client_data.get("id")
            or client_data.get("uuid")
            or client_uuid
        )

        # ------------------------------------------------------
        # Email واقعی
        # ------------------------------------------------------

        real_email = (
            client_data.get("email")
            or email
        )

        # ------------------------------------------------------
        # subId واقعی پنل
        # ------------------------------------------------------

        sub_id = (
            client_data.get("subId")
            or client_data.get("subID")
            or client_data.get("sub_id")
        )

        if not sub_id:
            raise SanaeiApiError(
                "کلاینت ساخته شد اما subId واقعی پنل دریافت نشد."
            )

        # ------------------------------------------------------
        # گرفتن لینک‌های واقعی پنل
        # ------------------------------------------------------

        subscription_links = await self.get_subscription_links(
            str(sub_id)
        )

        if not subscription_links:
            raise SanaeiApiError(
                "کلاینت ساخته شد اما هیچ لینک Subscription "
                "از پنل دریافت نشد."
            )

        # اولین لینک برای سازگاری با کد فعلی
        subscription_link = subscription_links[0]

        return {
            "client_uuid": str(real_uuid),
            "email": str(real_email),
            "sub_id": str(sub_id),
            "inbound_id": inbound_id,

            # لینک اصلی Subscription
            "subscription_link": subscription_link,

            # تمام کانفیگ‌های تکی
            "subscription_links": subscription_links,

            # پاسخ اصلی API
            "response": data,

            # اطلاعات واقعی client
            "client": client_data,
        }

    # ==========================================================
    # GET CLIENT
    # ==========================================================

    async def get_client(
        self,
        email: str,
    ) -> dict | None:

        email = quote(
            (email or "").strip(),
            safe="",
        )

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/get/{email}",
        )

        if not isinstance(data, dict):
            return None

        # ------------------------------------------------------
        # obj
        # ------------------------------------------------------

        obj = data.get("obj")

        if isinstance(obj, dict):
            return obj

        # ------------------------------------------------------
        # data
        # ------------------------------------------------------

        nested = data.get("data")

        if isinstance(nested, dict):

            if isinstance(
                nested.get("client"),
                dict,
            ):
                return nested["client"]

            return nested

        # ------------------------------------------------------
        # client
        # ------------------------------------------------------

        client = data.get("client")

        if isinstance(client, dict):
            return client

        return None

    # ==========================================================
    # SUBSCRIPTION LINKS
    #
    # API:
    # GET /panel/api/clients/subLinks/{subId}
    #
    # پاسخ رسمی:
    #
    # {
    #   "success": true,
    #   "obj": [
    #       "vless://...",
    #       "vmess://..."
    #   ]
    # }
    # ==========================================================

    async def get_subscription_links(
        self,
        sub_id: str,
    ) -> list[str]:

        sub_id = (sub_id or "").strip()

        if not sub_id:
            raise SanaeiApiError(
                "subId برای دریافت Subscription خالی است."
            )

        response = await self.client.get(
            f"{self.api_base}/clients/subLinks/"
            f"{quote(sub_id, safe='')}"
        )

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                "پاسخ API مربوط به Subscription معتبر نیست."
            )

        if response.status_code == 404:
            raise SanaeiApiError(
                "Endpoint دریافت Subscription در پنل پیدا نشد."
            )

        if response.status_code >= 400:
            raise SanaeiApiError(
                "خطا در دریافت Subscription:\n"
                f"HTTP: {response.status_code}\n"
                f"{data}"
            )

        if isinstance(data, dict):

            if data.get("success") is False:
                raise SanaeiApiError(
                    f"خطای پنل در دریافت Subscription: "
                    f"{data.get('msg', data)}"
                )

        # ------------------------------------------------------
        # ساختار اصلی Sanaei:
        #
        # data["obj"] = [
        #   "vless://...",
        #   "vmess://..."
        # ]
        # ------------------------------------------------------

        links = []

        if isinstance(data, dict):

            obj = data.get("obj")

            if isinstance(obj, list):
                links.extend(
                    item.strip()
                    for item in obj
                    if isinstance(item, str)
                    and item.strip()
                )

            elif isinstance(obj, str):
                if obj.strip():
                    links.append(
                        obj.strip()
                    )

        # ------------------------------------------------------
        # fallback برای نسخه‌های متفاوت API
        # ------------------------------------------------------

        if not links:
            links = self._extract_protocol_links(
                data
            )

        # حذف duplicate
        unique_links = []

        for link in links:

            if link not in unique_links:
                unique_links.append(link)

        if not unique_links:
            raise SanaeiApiError(
                "API پنل پاسخ داد اما هیچ کانفیگ/Subscription "
                "معتبری در پاسخ پیدا نشد.\n"
                f"Response: {data}"
            )

        return unique_links

    # ==========================================================
    # SINGLE SUBSCRIPTION LINK
    # ==========================================================

    async def get_subscription_link(
        self,
        sub_id: str,
    ) -> str:

        links = await self.get_subscription_links(
            sub_id
        )

        return links[0]

    # ==========================================================
    # EXTRACT PROTOCOL LINKS
    # ==========================================================

    @staticmethod
    def _extract_protocol_links(
        data,
    ) -> list[str]:

        protocols = (
            "vless://",
            "vmess://",
            "trojan://",
            "ss://",
            "hysteria://",
            "hysteria2://",
            "hy2://",
        )

        result: list[str] = []

        def walk(obj):

            if isinstance(obj, str):

                value = obj.strip()

                for protocol in protocols:

                    if value.startswith(protocol):
                        result.append(value)
                        return

            elif isinstance(obj, dict):

                for value in obj.values():
                    walk(value)

            elif isinstance(obj, list):

                for value in obj:
                    walk(value)

        walk(data)

        return result

    # ==========================================================
    # CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        email = quote(
            (email or "").strip(),
            safe="",
        )

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/traffic/{email}",
        )

        if isinstance(data, dict):

            obj = data.get("obj")

            if isinstance(obj, dict):
                return obj

        return None

    # ==========================================================
    # GET CLIENT LINKS
    #
    # این endpoint برای گرفتن کانفیگ‌های تکی
    # یک Client بسیار مناسب است.
    #
    # GET /panel/api/clients/links/{email}
    # ==========================================================

    async def get_client_links(
        self,
        email: str,
    ) -> list[str]:

        email = quote(
            (email or "").strip(),
            safe="",
        )

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/links/{email}",
        )

        if isinstance(data, dict):

            obj = data.get("obj")

            if isinstance(obj, list):

                return [
                    item.strip()
                    for item in obj
                    if isinstance(item, str)
                    and item.strip()
                ]

            if isinstance(obj, str):
                return [obj.strip()]

        links = self._extract_protocol_links(
            data
        )

        return list(dict.fromkeys(links))

    # ==========================================================
    # DELETE CLIENT
    # ==========================================================

    async def delete_client(
        self,
        email: str,
    ) -> None:

        email = quote(
            (email or "").strip(),
            safe="",
        )

        await self._request(
            "POST",
            f"{self.api_base}/clients/del/{email}",
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self) -> None:

        await self.client.aclose()


# ==============================================================
# LEGACY CONFIG LINK
#
# فعلاً استفاده نمی‌شود.
# لینک واقعی باید از خود پنل گرفته شود.
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