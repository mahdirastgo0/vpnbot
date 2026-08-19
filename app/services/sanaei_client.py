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
                f"پاسخ JSON معتبر نیست.\n"
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
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {response.url}\n"
                f"HTTP: 404"
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

            # بعضی نسخه‌های پنل:
            # {"success": false, "msg": "..."}
            if data.get("success") is not None:
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
            if inbound_id is not None
            else self.panel.inbound_id
        )

        if inbound_id is None:
            raise SanaeiApiError(
                "Inbound ID برای این پنل مشخص نشده است."
            )

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ / email خالی است."
            )

        # UUID واقعی Client
        client_uuid = str(uuid.uuid4())

        # زمان انقضا
        if duration_days > 0:
            expire_ms = int(
                (
                    datetime.now(timezone.utc)
                    + timedelta(days=duration_days)
                ).timestamp()
                * 1000
            )
        else:
            expire_ms = 0

        # حجم
        total_bytes = (
            traffic_gb * 1024 * 1024 * 1024
            if traffic_gb > 0
            else 0
        )

        # ======================================================
        # مهم:
        #
        # tgId باید عدد باشد
        # inboundIds باید خارج از client باشد
        # email همان اسم انتخاب‌شده توسط کاربر است
        # ======================================================

        client_obj = {
            "id": client_uuid,
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": 0,
            "subId": "",
        }

        payload = {
            "inboundIds": [int(inbound_id)],
            "client": client_obj,
        }

        data = await self._request(
            "POST",
            f"{self.api_base}/clients/add",
            json=payload,
        )

        # ======================================================
        # استخراج Client واقعی از پاسخ پنل
        # ======================================================

        client_data = self._extract_client(data)

        if client_data is None:
            # اگر API موفق بود ولی ساختار پاسخ متفاوت بود،
            # حداقل UUID خودمان را نگه می‌داریم.
            client_data = {}

        real_uuid = (
            client_data.get("id")
            or client_data.get("uuid")
            or client_uuid
        )

        real_email = (
            client_data.get("email")
            or email
        )

        # ======================================================
        # subId واقعی پنل
        # ======================================================

        sub_id = (
            client_data.get("subId")
            or client_data.get("subID")
            or client_data.get("sub_id")
        )

        # بعضی نسخه‌های پنل subId را داخل data/object می‌گذارند.
        if not sub_id:
            sub_id = self._find_value(
                data,
                (
                    "subId",
                    "subID",
                    "sub_id",
                ),
            )

        if not sub_id:
            raise SanaeiApiError(
                "کلاینت ساخته شد اما subId واقعی از پاسخ پنل دریافت نشد."
            )

        # ======================================================
        # Subscription واقعی پنل
        # ======================================================

        subscription_link = await self.get_subscription_link(
            str(sub_id)
        )

        return {
            "client_uuid": str(real_uuid),
            "email": str(real_email),
            "sub_id": str(sub_id),
            "inbound_id": int(inbound_id),
            "subscription_link": subscription_link,
            "response": data,
        }

    # ==========================================================
    # EXTRACT CLIENT
    # ==========================================================

    @staticmethod
    def _extract_client(data) -> dict | None:

        if isinstance(data, dict):

            # ساختار:
            # {"client": {...}}
            client = data.get("client")

            if isinstance(client, dict):
                return client

            # ساختار:
            # {"obj": {"client": {...}}}
            obj = data.get("obj")

            if isinstance(obj, dict):

                client = obj.get("client")

                if isinstance(client, dict):
                    return client

                # ممکن است خود obj کلاینت باشد
                if (
                    "email" in obj
                    or "subId" in obj
                    or "id" in obj
                ):
                    return obj

            # ساختار:
            # {"data": {"client": {...}}}
            nested = data.get("data")

            if isinstance(nested, dict):

                client = nested.get("client")

                if isinstance(client, dict):
                    return client

                if (
                    "email" in nested
                    or "subId" in nested
                    or "id" in nested
                ):
                    return nested

            # خود data
            if (
                "email" in data
                or "subId" in data
                or "id" in data
            ):
                return data

        return None

    # ==========================================================
    # FIND VALUE
    # ==========================================================

    @staticmethod
    def _find_value(
        obj,
        keys: tuple[str, ...],
    ):

        if isinstance(obj, dict):

            for key in keys:
                if key in obj:
                    value = obj[key]

                    if value not in (
                        None,
                        "",
                    ):
                        return value

            for value in obj.values():

                result = SanaeiClient._find_value(
                    value,
                    keys,
                )

                if result not in (
                    None,
                    "",
                ):
                    return result

        elif isinstance(obj, list):

            for item in obj:

                result = SanaeiClient._find_value(
                    item,
                    keys,
                )

                if result not in (
                    None,
                    "",
                ):
                    return result

        return None

    # ==========================================================
    # SUBSCRIPTION LINK
    # ==========================================================

    async def get_subscription_link(
        self,
        sub_id: str,
    ) -> str:

        if not sub_id:
            raise SanaeiApiError(
                "subId برای دریافت Subscription خالی است."
            )

        response = await self.client.get(
            f"{self.api_base}/clients/subLinks/{quote(str(sub_id))}"
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
                f"خطا در دریافت Subscription "
                f"(HTTP {response.status_code}): {data}"
            )

        link = self._extract_subscription_link(data)

        if not link:
            raise SanaeiApiError(
                "API پنل پاسخ داد اما لینک Subscription "
                "در پاسخ پیدا نشد."
            )

        return link

    # ==========================================================
    # EXTRACT SUBSCRIPTION LINK
    # ==========================================================

    @staticmethod
    def _extract_subscription_link(
        data,
    ) -> str | None:

        if isinstance(data, str):

            value = data.strip()

            if (
                value.startswith("http://")
                or value.startswith("https://")
            ):
                return value

            return None

        if isinstance(data, list):

            for item in data:

                result = SanaeiClient._extract_subscription_link(
                    item
                )

                if result:
                    return result

            return None

        if isinstance(data, dict):

            # کلیدهای رایج
            possible_keys = (
                "subscription",
                "subscriptionLink",
                "subscriptionUrl",
                "subscriptionURL",
                "subLink",
                "subUrl",
                "subURL",
                "url",
                "link",
                "sub",
            )

            for key in possible_keys:

                if key in data:

                    result = (
                        SanaeiClient
                        ._extract_subscription_link(
                            data[key]
                        )
                    )

                    if result:
                        return result

            # ساختارهای تو در تو
            for key in (
                "data",
                "obj",
                "result",
                "response",
            ):

                if key in data:

                    result = (
                        SanaeiClient
                        ._extract_subscription_link(
                            data[key]
                        )
                    )

                    if result:
                        return result

            # جستجوی عمیق
            for value in data.values():

                result = (
                    SanaeiClient
                    ._extract_subscription_link(
                        value
                    )
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
        await self.client.aclose()


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