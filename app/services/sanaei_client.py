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

        self._client = httpx.AsyncClient(
            base_url=panel.url,
            verify=False,
            timeout=30.0,
        )

        self._logged_in = False

    # =========================================================
    # URL
    # =========================================================

    def _api_path(
        self,
        path: str,
    ) -> str:

        path = path.lstrip("/")

        return (
            f"{self.panel.api_base_path}/{path}"
        )

    # =========================================================
    # LOGIN
    # =========================================================

    async def login(self) -> None:

        if self._logged_in:
            return

        try:

            response = await self._client.post(
                "/login",
                json={
                    "username": self.panel.username,
                    "password": self.panel.password,
                },
            )

        except httpx.HTTPError as exc:

            raise SanaeiApiError(
                f"اتصال به پنل «{self.panel.name}» "
                f"ناموفق بود: {exc}"
            ) from exc

        if response.status_code != 200:

            raise SanaeiApiError(
                f"ورود به پنل «{self.panel.name}» "
                f"ناموفق بود. HTTP {response.status_code}"
            )

        try:
            data = response.json()

        except ValueError as exc:

            raise SanaeiApiError(
                "پاسخ لاگین پنل JSON معتبر نبود."
            ) from exc

        if not data.get("success"):

            raise SanaeiApiError(
                f"لاگین پنل «{self.panel.name}» شکست خورد: "
                f"{data.get('msg', 'خطای نامشخص')}"
            )

        self._logged_in = True

    # =========================================================
    # REQUEST
    # =========================================================

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:

        await self.login()

        api_path = self._api_path(path)

        response = await self._client.request(
            method,
            api_path,
            **kwargs,
        )

        # Session expired
        if response.status_code in (
            401,
            403,
        ):

            self._logged_in = False

            await self.login()

            response = await self._client.request(
                method,
                api_path,
                **kwargs,
            )

        if response.status_code >= 400:

            text = response.text[:1000]

            raise SanaeiApiError(
                f"خطای API پنل «{self.panel.name}»\n"
                f"HTTP: {response.status_code}\n"
                f"Path: {api_path}\n"
                f"Response: {text}"
            )

        try:

            data = response.json()

        except ValueError as exc:

            raise SanaeiApiError(
                f"پاسخ API پنل JSON معتبر نیست.\n"
                f"HTTP: {response.status_code}\n"
                f"Response: {response.text[:500]}"
            ) from exc

        if not isinstance(data, dict):

            raise SanaeiApiError(
                "فرمت پاسخ API پنل نامعتبر است."
            )

        if data.get("success") is False:

            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', 'خطای نامشخص')}"
            )

        return data

    # =========================================================
    # INBOUNDS
    # =========================================================

    async def list_inbounds(
        self,
    ) -> list[dict]:

        data = await self._request(
            "GET",
            "/inbounds/list",
        )

        obj = data.get("obj")

        if not isinstance(obj, list):

            return []

        return obj

    async def get_inbound(
        self,
        inbound_id: int | None = None,
    ) -> dict:

        inbound_id = (
            inbound_id
            or self.panel.inbound_id
        )

        data = await self._request(
            "GET",
            f"/inbounds/get/{inbound_id}",
        )

        obj = data.get("obj")

        if not obj:

            raise SanaeiApiError(
                f"اینباند {inbound_id} "
                f"روی پنل پیدا نشد."
            )

        return obj

    # =========================================================
    # ADD CLIENT
    # =========================================================

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
        client_uuid: str | None = None,
    ) -> dict:

        inbound_id = (
            inbound_id
            or self.panel.inbound_id
        )

        client_uuid = (
            client_uuid
            or str(uuid.uuid4())
        )

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
            "flow": "",
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": uuid.uuid4().hex[:16],
            "comment": "",
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps(
                {
                    "clients": [
                        client_obj
                    ]
                },
                separators=(",", ":"),
            ),
        }

        data = await self._request(
            "POST",
            "/inbounds/addClient",
            json=payload,
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound_id": inbound_id,
            "response": data,
            "expire_ms": expire_ms,
            "traffic_bytes": total_bytes,
        }

    # =========================================================
    # DELETE CLIENT
    # =========================================================

    async def delete_client(
        self,
        inbound_id: int,
        client_uuid: str,
    ) -> None:

        await self._request(
            "POST",
            f"/inbounds/{inbound_id}/delClient/{client_uuid}",
        )

    # =========================================================
    # CLIENT TRAFFIC
    # =========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"/inbounds/getClientTraffics/{quote(email)}",
        )

        return data.get("obj")

    # =========================================================
    # CLIENT TRAFFIC BY UUID
    # =========================================================

    async def get_client_traffic_by_id(
        self,
        client_uuid: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"/inbounds/getClientTrafficsById/{client_uuid}",
        )

        return data.get("obj")

    # =========================================================
    # CLOSE
    # =========================================================

    async def close(self) -> None:

        await self._client.aclose()

        self._logged_in = False


# =============================================================
# CONFIG LINK
# =============================================================

def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    stream_settings_raw = (
        inbound.get("streamSettings")
        or "{}"
    )

    if isinstance(
        stream_settings_raw,
        str,
    ):

        try:

            stream_settings = json.loads(
                stream_settings_raw
            )

        except json.JSONDecodeError:

            stream_settings = {}

    else:

        stream_settings = (
            stream_settings_raw
            or {}
        )

    network = stream_settings.get(
        "network",
        "tcp",
    )

    security = stream_settings.get(
        "security",
        "none",
    )

    port = inbound.get("port")

    if not port:

        raise SanaeiApiError(
            "پورت اینباند مشخص نیست."
        )

    # ---------------------------------------------------------
    # host
    # ---------------------------------------------------------

    host = (
        panel.url
        .split("://", 1)[-1]
        .split("/", 1)[0]
        .split(":", 1)[0]
    )

    remark = quote(
        f"{panel.name}-{email}"
    )

    # =========================================================
    # VLESS
    # =========================================================

    if panel.protocol == "vless":

        params = [
            f"type={quote(str(network))}",
            f"security={quote(str(security))}",
        ]

        # -----------------------------------------------------
        # WebSocket
        # -----------------------------------------------------

        if network == "ws":

            ws_settings = (
                stream_settings.get(
                    "wsSettings"
                )
                or {}
            )

            path = ws_settings.get(
                "path",
                "/",
            )

            headers = (
                ws_settings.get(
                    "headers"
                )
                or {}
            )

            params.append(
                "path="
                + quote(
                    path,
                    safe="",
                )
            )

            if headers.get("Host"):

                params.append(
                    "host="
                    + quote(
                        headers["Host"],
                        safe="",
                    )
                )

        # -----------------------------------------------------
        # HTTP/2
        # -----------------------------------------------------

        elif network == "h2":

            h2_settings = (
                stream_settings.get(
                    "httpSettings"
                )
                or {}
            )

            path = h2_settings.get(
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

            host_list = h2_settings.get(
                "host",
                [],
            )

            if isinstance(
                host_list,
                list,
            ) and host_list:

                params.append(
                    "host="
                    + quote(
                        host_list[0],
                        safe="",
                    )
                )

        # -----------------------------------------------------
        # TLS
        # -----------------------------------------------------

        if security == "tls":

            tls_settings = (
                stream_settings.get(
                    "tlsSettings"
                )
                or {}
            )

            server_name = tls_settings.get(
                "serverName"
            )

            if server_name:

                params.append(
                    "sni="
                    + quote(
                        server_name,
                        safe="",
                    )
                )

        # -----------------------------------------------------
        # Reality
        # -----------------------------------------------------

        elif security == "reality":

            reality_settings = (
                stream_settings.get(
                    "realitySettings"
                )
                or {}
            )

            settings = (
                reality_settings.get(
                    "settings"
                )
                or {}
            )

            server_name = (
                reality_settings.get(
                    "serverNames",
                    [host],
                )
            )

            if isinstance(
                server_name,
                list,
            ) and server_name:

                params.append(
                    "sni="
                    + quote(
                        server_name[0],
                        safe="",
                    )
                )

            public_key = settings.get(
                "publicKey"
            )

            short_id = settings.get(
                "shortIds"
            )

            if public_key:

                params.append(
                    "pbk="
                    + quote(
                        public_key,
                        safe="",
                    )
                )

            if isinstance(
                short_id,
                list,
            ) and short_id:

                params.append(
                    "sid="
                    + quote(
                        short_id[0],
                        safe="",
                    )
                )

            spider_x = settings.get(
                "spiderX"
            )

            if spider_x:

                params.append(
                    "spx="
                    + quote(
                        spider_x,
                        safe="",
                    )
                )

        query = "&".join(params)

        return (
            f"vless://"
            f"{client_uuid}@"
            f"{host}:{port}"
            f"?{query}"
            f"#{remark}"
        )

    # =========================================================
    # VMESS
    # =========================================================

    vmess_obj = {
        "v": "2",
        "ps": f"{panel.name}-{email}",
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
        "sni": "",
    }

    if network == "ws":

        ws_settings = (
            stream_settings.get(
                "wsSettings"
            )
            or {}
        )

        vmess_obj["path"] = ws_settings.get(
            "path",
            "/",
        )

        headers = (
            ws_settings.get(
                "headers"
            )
            or {}
        )

        vmess_obj["host"] = headers.get(
            "Host",
            "",
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