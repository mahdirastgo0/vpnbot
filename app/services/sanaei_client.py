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

        self._client = httpx.AsyncClient(
            base_url=self.panel.url,
            verify=False,
            timeout=30,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.panel.api_token}",
            },
        )

    # ==========================================================
    # API URL
    # ==========================================================

    def _api(self, path: str) -> str:
        path = path.lstrip("/")

        return (
            f"{self.panel.api_base_path.rstrip('/')}"
            f"/{path}"
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

        url = self._api(path)

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

        if response.status_code in (401, 403):

            raise SanaeiApiError(
                f"احراز هویت API پنل «{self.panel.name}» رد شد. "
                f"API Token یا مسیر API را بررسی کن."
            )

        try:
            data = response.json()
        except Exception:

            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {response.status_code}): "
                f"{response.text[:500]}"
            )

        if response.status_code >= 400:

            raise SanaeiApiError(
                f"خطای HTTP {response.status_code} از پنل "
                f"«{self.panel.name}»: "
                f"{data.get('msg', response.text)}"
            )

        if not data.get("success", True):

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
        در معماری API Token نیازی به username/password نیست.

        این تابع فقط برای سازگاری با کدهای قدیمی پروژه باقی مانده
        و وضعیت احراز هویت API Token را بررسی می‌کند.
        """

        try:
            await self.list_inbounds()
            return True

        except SanaeiApiError:
            raise

    # ==========================================================
    # INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            "inbounds/list",
        )

        obj = data.get("obj")

        if not obj:
            return []

        if isinstance(obj, list):
            return obj

        return []

    async def get_inbound(
        self,
        inbound_id: int | None = None,
    ) -> dict:

        inbound_id = inbound_id or self.panel.inbound_id

        inbounds = await self.list_inbounds()

        inbound = next(
            (
                item
                for item in inbounds
                if int(item.get("id", -1)) == int(inbound_id)
            ),
            None,
        )

        if inbound is None:
            raise SanaeiApiError(
                f"اینباند {inbound_id} "
                f"روی پنل «{self.panel.name}» پیدا نشد."
            )

        return inbound

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

        inbound_id = inbound_id or self.panel.inbound_id

        client_uuid = str(uuid.uuid4())

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
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": uuid.uuid4().hex[:16],
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

        await self._request(
            "POST",
            "inbounds/addClient",
            json=payload,
        )

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
            f"getClientTraffics/{quote(email, safe='')}",
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
        .split("://", 1)[-1]
        .split("/", 1)[0]
        .split(":", 1)[0]
    )

    port = inbound.get("port")

    remark = quote(
        f"{panel.name}-{email}",
        safe="",
    )

    # ----------------------------------------------------------
    # VLESS
    # ----------------------------------------------------------

    if panel.protocol == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        # TLS
        if security == "tls":

            params.append(
                "sni=" + quote(host, safe="")
            )

        # WS
        if network == "ws":

            ws_settings = stream_settings.get(
                "wsSettings",
                {},
            )

            path = ws_settings.get(
                "path",
                "/",
            )

            params.append(
                "path=" + quote(
                    path,
                    safe="/",
                )
            )

            headers = ws_settings.get(
                "headers",
                {},
            )

            ws_host = headers.get(
                "Host"
            )

            if ws_host:

                params.append(
                    "host=" + quote(
                        ws_host,
                        safe="",
                    )
                )

        # TCP + Reality
        if security == "reality":

            reality = stream_settings.get(
                "realitySettings",
                {},
            )

            reality_settings = reality.get(
                "settings",
                {},
            )

            public_key = (
                reality_settings.get(
                    "publicKey"
                )
                or reality_settings.get(
                    "pbk"
                )
            )

            short_id = (
                reality_settings.get(
                    "shortId"
                )
                or reality_settings.get(
                    "sid"
                )
            )

            server_name = (
                reality.get(
                    "serverName"
                )
                or reality_settings.get(
                    "serverName"
                )
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

            params.append(
                "fp=chrome"
            )

        query = "&".join(params)

        return (
            f"vless://{client_uuid}"
            f"@{host}:{port}"
            f"?{query}"
            f"#{remark}"
        )

    # ----------------------------------------------------------
    # VMESS
    # ----------------------------------------------------------

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

        ws_settings = stream_settings.get(
            "wsSettings",
            {},
        )

        vmess_obj["path"] = ws_settings.get(
            "path",
            "",
        )

        vmess_obj["host"] = (
            ws_settings
            .get("headers", {})
            .get("Host", "")
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