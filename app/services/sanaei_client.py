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

    def __init__(self, panel: PanelConfig):
        self.panel = panel

        self.base_url = panel.url.rstrip("/")
        self.api_base = (
            f"{self.base_url}"
            f"{panel.api_base_path.rstrip('/')}"
        )

        self._client = httpx.AsyncClient(
            verify=False,
            timeout=30,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {panel.api_token}",
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

        url = f"{self.api_base}/{path.lstrip('/')}"

        try:
            response = await self._client.request(
                method,
                url,
                **kwargs,
            )

        except httpx.HTTPError as exc:
            raise SanaeiApiError(
                f"خطا در اتصال به پنل «{self.panel.name}»: {exc}"
            ) from exc

        # ------------------------------------------------------
        # Auth
        # ------------------------------------------------------

        if response.status_code in (401, 403):
            raise SanaeiApiError(
                f"احراز هویت API پنل «{self.panel.name}» رد شد."
            )

        # ------------------------------------------------------
        # 404
        # ------------------------------------------------------

        if response.status_code == 404:
            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {url}\n"
                f"HTTP: 404"
            )

        # ------------------------------------------------------
        # Other HTTP errors
        # ------------------------------------------------------

        if response.status_code >= 400:
            raise SanaeiApiError(
                f"خطای HTTP {response.status_code} از پنل "
                f"«{self.panel.name}»:\n"
                f"{response.text[:1000]}"
            )

        # ------------------------------------------------------
        # JSON
        # ------------------------------------------------------

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ غیر JSON از پنل «{self.panel.name}»:\n"
                f"{response.text[:1000]}"
            )

        # ------------------------------------------------------
        # API success
        # ------------------------------------------------------

        if data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', 'Unknown error')}"
            )

        return data

    # ==========================================================
    # LOGIN
    # ==========================================================

    async def login(self) -> bool:
        """
        احراز هویت با API Token.
        username/password استفاده نمی‌شود.
        """

        await self.list_inbounds()
        return True

    # ==========================================================
    # LIST INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            "inbounds/list",
        )

        obj = data.get("obj")

        if isinstance(obj, list):
            return obj

        return []

    # ==========================================================
    # GET INBOUND
    # ==========================================================

    async def get_inbound(
        self,
        inbound_id: int | None = None,
    ) -> dict:

        inbound_id = (
            inbound_id
            or self.panel.inbound_id
        )

        # ابتدا endpoint مستقیم get را امتحان می‌کنیم
        try:
            data = await self._request(
                "GET",
                f"inbounds/get/{inbound_id}",
            )

            obj = data.get("obj")

            if isinstance(obj, dict):
                return obj

        except SanaeiApiError:
            pass

        # fallback به list
        inbounds = await self.list_inbounds()

        for inbound in inbounds:
            if int(inbound.get("id", -1)) == int(inbound_id):
                return inbound

        raise SanaeiApiError(
            f"اینباند {inbound_id} روی پنل "
            f"«{self.panel.name}» پیدا نشد."
        )

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

        # ------------------------------------------------------
        # UUID
        # ------------------------------------------------------

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # Expiry
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Traffic
        # ------------------------------------------------------

        total_bytes = (
            traffic_gb
            * 1024
            * 1024
            * 1024
            if traffic_gb > 0
            else 0
        )

        # ------------------------------------------------------
        # Client
        # ------------------------------------------------------

        client = {
            "id": client_uuid,
            "flow": "",
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": uuid.uuid4().hex[:16],
        }

        # ------------------------------------------------------
        # 3X-UI addClient format
        # ------------------------------------------------------

        payload = {
            "id": int(inbound_id),
            "settings": json.dumps(
                {
                    "clients": [client]
                },
                separators=(",", ":"),
            ),
        }

        # ------------------------------------------------------
        # Send
        # ------------------------------------------------------

        await self._request(
            "POST",
            "inbounds/addClient",
            json=payload,
        )

        # ------------------------------------------------------
        # Get inbound after creation
        # ------------------------------------------------------

        inbound = await self.get_inbound(
            inbound_id
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound": inbound,
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
            f"inbounds/getClientTraffics/{quote(email, safe='')}",
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
            f"inbounds/{inbound_id}/delClient/{client_uuid}",
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self) -> None:

        if not self._client.is_closed:
            await self._client.aclose()


# ==============================================================
# CONFIG LINK
# ==============================================================

def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    # ----------------------------------------------------------
    # Parse stream settings
    # ----------------------------------------------------------

    raw_stream = inbound.get(
        "streamSettings"
    )

    if isinstance(raw_stream, str):

        try:
            stream_settings = json.loads(
                raw_stream
            )
        except Exception:
            stream_settings = {}

    elif isinstance(raw_stream, dict):

        stream_settings = raw_stream

    else:
        stream_settings = {}

    # ----------------------------------------------------------
    # Network / Security
    # ----------------------------------------------------------

    network = stream_settings.get(
        "network",
        "tcp",
    )

    security = stream_settings.get(
        "security",
        "none",
    )

    # ----------------------------------------------------------
    # Host
    # ----------------------------------------------------------

    host = (
        panel.url
        .split("://", 1)[-1]
        .split("/", 1)[0]
        .split(":", 1)[0]
    )

    port = inbound.get("port")

    remark = quote(
        f"{panel.name}-{email}",
        safe="",
    )

    # ==========================================================
    # VLESS
    # ==========================================================

    if panel.protocol == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        # TLS
        if security == "tls":

            params.append(
                "sni=" + quote(
                    host,
                    safe="",
                )
            )

        # WS
        if network == "ws":

            ws = stream_settings.get(
                "wsSettings",
                {},
            )

            path = ws.get(
                "path",
                "/",
            )

            params.append(
                "path=" + quote(
                    path,
                    safe="/",
                )
            )

            ws_headers = ws.get(
                "headers",
                {},
            )

            ws_host = ws_headers.get(
                "Host"
            )

            if ws_host:

                params.append(
                    "host=" + quote(
                        ws_host,
                        safe="",
                    )
                )

        # Reality
        if security == "reality":

            reality = stream_settings.get(
                "realitySettings",
                {},
            )

            settings_obj = reality.get(
                "settings",
                {},
            )

            public_key = (
                settings_obj.get("publicKey")
                or settings_obj.get("pbk")
            )

            short_id = (
                settings_obj.get("shortId")
                or settings_obj.get("sid")
            )

            server_name = (
                reality.get("serverName")
                or settings_obj.get("serverName")
            )

            if public_key:

                params.append(
                    "pbk=" + quote(
                        public_key,
                        safe="",
                    )
                )

            if short_id:

                params.append(
                    "sid=" + quote(
                        short_id,
                        safe="",
                    )
                )

            if server_name:

                params.append(
                    "sni=" + quote(
                        server_name,
                        safe="",
                    )
                )

            params.append("fp=chrome")

        query = "&".join(params)

        return (
            f"vless://{client_uuid}"
            f"@{host}:{port}"
            f"?{query}"
            f"#{remark}"
        )

    # ==========================================================
    # VMESS
    # ==========================================================

    vmess_obj = {
        "v": "2",
        "ps": f"{panel.name}-{email}",
        "add": host,
        "port": port,
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

        ws = stream_settings.get(
            "wsSettings",
            {},
        )

        vmess_obj["path"] = ws.get(
            "path",
            "",
        )

        vmess_obj["host"] = (
            ws.get(
                "headers",
                {},
            ).get(
                "Host",
                "",
            )
        )

    if security == "tls":
        vmess_obj["tls"] = "tls"

    raw = json.dumps(
        vmess_obj,
        separators=(",", ":"),
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )