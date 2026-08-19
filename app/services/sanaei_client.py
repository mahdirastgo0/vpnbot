from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from app.config import PanelConfig


class SanaeiApiError(RuntimeError):
    pass


class SanaeiClient:

    def __init__(
        self,
        panel: PanelConfig,
    ) -> None:

        self.panel = panel

        base_url = (
            panel.url.rstrip("/")
            + "/"
        )

        self.client = httpx.AsyncClient(

            base_url=base_url,

            verify=False,

            timeout=30,

            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization":
                    f"Bearer {panel.api_token}",
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

        try:

            response = await self.client.request(
                method,
                path.lstrip("/"),
                **kwargs,
            )

        except httpx.HTTPError as exc:

            raise SanaeiApiError(
                f"ارتباط با پنل «{self.panel.name}» برقرار نشد:\n"
                f"{exc}"
            ) from exc

        if response.status_code == 401:

            raise SanaeiApiError(
                f"API Token پنل «{self.panel.name}» "
                f"رد شد."
            )

        if response.status_code == 403:

            raise SanaeiApiError(
                f"دسترسی به API پنل «{self.panel.name}» "
                f"مجاز نیست."
            )

        if response.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint پیدا نشد.\n\n"
                f"Panel: {self.panel.name}\n"
                f"URL: {response.url}\n"
                f"HTTP: 404"
            )

        if response.status_code >= 400:

            raise SanaeiApiError(
                f"خطای API پنل «{self.panel.name}»\n"
                f"HTTP: {response.status_code}\n"
                f"{response.text[:1000]}"
            )

        try:

            data = response.json()

        except Exception as exc:

            raise SanaeiApiError(
                "پاسخ API پنل JSON معتبر نیست:\n"
                f"{response.text[:1000]}"
            ) from exc

        if isinstance(data, dict):

            if data.get("success") is False:

                raise SanaeiApiError(
                    f"خطای پنل «{self.panel.name}»:\n"
                    f"{data.get('msg', 'خطای نامشخص')}"
                )

        return data

    # ==========================================================
    # TEST CONNECTION
    # ==========================================================

    async def test_connection(self) -> dict:

        """
        برای تست Token و endpoint.

        توجه:
        مسیر این endpoint را می‌توان از ENV تغییر داد.
        """

        return await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/list",
        )

    # ==========================================================
    # LIST INBOUNDS
    # ==========================================================

    async def list_inbounds(
        self,
    ) -> list[dict]:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/list",
        )

        obj = data.get(
            "obj",
            [],
        )

        if isinstance(obj, list):
            return obj

        return []

    # ==========================================================
    # GET INBOUND
    # ==========================================================

    async def get_inbound(
        self,
        inbound_id: int,
    ) -> dict:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}"
            f"/inbounds/get/{inbound_id}",
        )

        obj = data.get("obj")

        if not obj:

            raise SanaeiApiError(
                f"Inbound #{inbound_id} پیدا نشد."
            )

        return obj

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

        client_uuid = str(
            uuid.uuid4()
        )

        sub_id = uuid.uuid4().hex[:16]

        now = datetime.now(
            timezone.utc
        )

        expire_at = (
            now
            + timedelta(
                days=duration_days
            )
        )

        expire_ms = int(
            expire_at.timestamp()
            * 1000
        )

        total_bytes = (
            traffic_gb
            * 1024
            * 1024
            * 1024
        )

        client = {

            "id": client_uuid,

            "email": email,

            "limitIp": 0,

            "totalGB": total_bytes,

            "expiryTime": expire_ms,

            "enable": True,

            "tgId": "",

            "subId": sub_id,
        }

        payload = {

            "id": inbound_id,

            "settings": json.dumps(
                {
                    "clients": [
                        client
                    ]
                },
                separators=(
                    ",",
                    ":",
                ),
            ),
        }

        data = await self._request(

            "POST",

            f"{self.panel.api_base_path}"
            "/inbounds/addClient",

            json=payload,
        )

        return {
            "success": True,
            "data": data,
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": sub_id,
            "expire_at": expire_at,
            "traffic_gb": traffic_gb,
            "inbound_id": inbound_id,
        }

    # ==========================================================
    # CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(

            "GET",

            f"{self.panel.api_base_path}"
            f"/inbounds/getClientTraffics/"
            f"{quote(email, safe='')}",
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
    # BUILD CONFIG
    # ==========================================================

    async def close(self) -> None:

        await self.client.aclose()


def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    stream_settings_raw = (
        inbound.get(
            "streamSettings"
        )
        or "{}"
    )

    try:

        stream_settings = json.loads(
            stream_settings_raw
        )

    except Exception:

        stream_settings = {}

    network = stream_settings.get(
        "network",
        "tcp",
    )

    security = stream_settings.get(
        "security",
        "none",
    )

    # ----------------------------------------------------------
    # آدرس سرور
    # ----------------------------------------------------------

    host = (
        inbound.get("listen")
        or inbound.get("address")
        or panel.url.split("://")[-1]
        .split(":")[0]
    )

    port = inbound.get(
        "port"
    )

    remark = quote(
        f"{panel.name}-{email}"
    )

    # ==========================================================
    # VLESS
    # ==========================================================

    if panel.protocol.lower() == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        # TLS
        if security == "tls":

            tls_settings = (
                stream_settings.get(
                    "tlsSettings",
                    {}
                )
            )

            server_name = (
                tls_settings.get(
                    "serverName"
                )
                or host
            )

            params.append(
                "sni="
                + quote(
                    server_name
                )
            )

        # WS
        if network == "ws":

            ws_settings = (
                stream_settings.get(
                    "wsSettings",
                    {}
                )
            )

            path = ws_settings.get(
                "path",
                "/",
            )

            params.append(
                "path="
                + quote(
                    path,
                    safe="",
                )
            )

            ws_headers = (
                ws_settings.get(
                    "headers",
                    {}
                )
            )

            ws_host = ws_headers.get(
                "Host"
            )

            if ws_host:

                params.append(
                    "host="
                    + quote(
                        ws_host
                    )
                )

        query = "&".join(
            params
        )

        return (
            f"vless://"
            f"{client_uuid}@"
            f"{host}:"
            f"{port}?"
            f"{query}#"
            f"{remark}"
        )

    # ==========================================================
    # VMESS
    # ==========================================================

    vmess = {

        "v": "2",

        "ps":
            f"{panel.name}-{email}",

        "add": host,

        "port": str(port),

        "id": client_uuid,

        "aid": "0",

        "scy": "auto",

        "net": network,

        "type": "none",

        "host": "",

        "path": "",

        "tls": "",
    }

    if network == "ws":

        ws_settings = (
            stream_settings.get(
                "wsSettings",
                {}
            )
        )

        vmess["path"] = (
            ws_settings.get(
                "path",
                "/",
            )
        )

        vmess["host"] = (
            ws_settings
            .get(
                "headers",
                {}
            )
            .get(
                "Host",
                "",
            )
        )

    if security == "tls":

        vmess["tls"] = "tls"

    raw = json.dumps(
        vmess,
        separators=(
            ",",
            ":",
        ),
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(
            raw
        ).decode()
    )