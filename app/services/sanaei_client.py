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

        response = await self._client.request(
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

        # UUID واقعی VLESS
        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # حجم
        # ------------------------------------------------------

        if traffic_gb and traffic_gb > 0:
            total_bytes = (
                traffic_gb
                * 1024
                * 1024
                * 1024
            )
        else:
            total_bytes = 0

        # ------------------------------------------------------
        # تاریخ انقضا
        # ------------------------------------------------------

        if duration_days and duration_days > 0:
            expire_ms = int(
                (
                    datetime.now(timezone.utc)
                    + timedelta(days=duration_days)
                ).timestamp()
                * 1000
            )
        else:
            expire_ms = 0

        # ------------------------------------------------------
        # مهم:
        #
        # subId را خودمان می‌سازیم تا کلاینت Subscription داشته
        # باشد. ولی بعد از ساخت، subId واقعی را از خود پنل
        # با GET client دریافت می‌کنیم.
        # ------------------------------------------------------

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

        payload = {
            "inboundIds": [
                int(inbound_id)
            ],
            "client": client_obj,
        }

        # ------------------------------------------------------
        # ساخت کلاینت
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            f"{self.api_base}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # پنل ممکن است subId را در پاسخ POST ندهد.
        # بنابراین کلاینت را با email از خود پنل می‌خوانیم.
        # ------------------------------------------------------

        actual_client = await self.get_client(
            email
        )

        if not actual_client:
            raise SanaeiApiError(
                "کلاینت ساخته شد اما اطلاعات آن از پنل قابل دریافت نیست."
            )

        # UUID واقعی
        actual_uuid = (
            actual_client.get("id")
            or actual_client.get("uuid")
            or client_uuid
        )

        # subId واقعی پنل
        actual_sub_id = (
            actual_client.get("subId")
            or actual_client.get("subID")
            or actual_client.get("sub_id")
        )

        if not actual_sub_id:
            raise SanaeiApiError(
                "کلاینت ساخته شد اما subId واقعی از پنل دریافت نشد."
            )

        # ------------------------------------------------------
        # لینک‌های تکی کلاینت
        # ------------------------------------------------------

        individual_links = await self.get_client_links(
            email
        )

        # ------------------------------------------------------
        # Subscription
        # ------------------------------------------------------

        subscription_link = None

        try:
            subscription_link = (
                await self.get_subscription_link(
                    actual_sub_id
                )
            )
        except SanaeiApiError:
            # ممکن است subLinks خالی باشد؛
            # کلاینت همچنان ساخته شده است.
            subscription_link = None

        return {
            "client_uuid": str(actual_uuid),
            "email": email,
            "sub_id": str(actual_sub_id),
            "inbound_id": int(inbound_id),

            "subscription_link": subscription_link,

            "individual_links": individual_links,

            "response": data,
            "client": actual_client,
        }

    # ==========================================================
    # GET CLIENT
    # ==========================================================

    async def get_client(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/get/{quote(email)}",
        )

        if not isinstance(data, dict):
            return None

        obj = data.get("obj")

        if isinstance(obj, dict):
            return obj

        return None

    # ==========================================================
    # GET CLIENT LINKS
    #
    # این endpoint لینک‌های واقعی VLESS/VMess/... را می‌دهد.
    # ==========================================================

    async def get_client_links(
        self,
        email: str,
    ) -> list[str]:

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/links/{quote(email)}",
        )

        if not isinstance(data, dict):
            return []

        obj = data.get("obj")

        if not isinstance(obj, list):
            return []

        links = []

        for item in obj:
            if isinstance(item, str):
                item = item.strip()

                if item.startswith(
                    (
                        "vless://",
                        "vmess://",
                        "trojan://",
                        "ss://",
                        "hy2://",
                        "hysteria://",
                    )
                ):
                    links.append(item)

        return links

    # ==========================================================
    # GET SUBSCRIPTION LINKS
    # ==========================================================

    async def get_subscription_links(
        self,
        sub_id: str,
    ) -> list[str]:

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/subLinks/{quote(str(sub_id))}",
        )

        if not isinstance(data, dict):
            return []

        obj = data.get("obj")

        if not isinstance(obj, list):
            return []

        links = []

        for item in obj:
            if isinstance(item, str):
                item = item.strip()

                if item.startswith(
                    (
                        "vless://",
                        "vmess://",
                        "trojan://",
                        "ss://",
                        "hy2://",
                        "hysteria://",
                    )
                ):
                    links.append(item)

        return links

    # ==========================================================
    # GET SUBSCRIPTION LINK
    #
    # برای لینک subscription واقعی:
    #
    # https://DOMAIN/sub/SUB_ID
    #
    # ==========================================================

    async def get_subscription_link(
        self,
        sub_id: str,
    ) -> str | None:

        links = await self.get_subscription_links(
            sub_id
        )

        # اگر API subLinks آرایه خالی داد،
        # این endpoint به معنی "لینک subscription"
        # نیست و نباید از آن URL جعلی بسازیم.
        #
        # بنابراین فعلاً None برمی‌گردانیم.
        if not links:
            return None

        return links[0]

    # ==========================================================
    # SUBSCRIPTION URL
    #
    # این تابع URL واقعی /sub/{subId} را می‌سازد.
    # آدرس subscription از تنظیمات پنل می‌آید.
    # ==========================================================

    def build_subscription_url(
        self,
        sub_id: str,
    ) -> str:

        # اگر پنل subscription_url داشته باشد
        subscription_base = getattr(
            self.panel,
            "subscription_url",
            None,
        )

        if subscription_base:
            return (
                subscription_base.rstrip("/")
                + "/"
                + quote(str(sub_id))
            )

        # fallback
        #
        # اگر subscription روی همان دامنه پنل باشد
        base_url = self.panel.url.rstrip("/")

        return (
            f"{base_url}/sub/"
            f"{quote(str(sub_id))}"
        )

    # ==========================================================
    # CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.api_base}/clients/traffic/{quote(email)}",
        )

        if isinstance(data, dict):
            obj = data.get("obj")

            if isinstance(obj, dict):
                return obj

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
# LEGACY
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