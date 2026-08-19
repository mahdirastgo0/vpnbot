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
            base_url=panel.url.rstrip("/"),
            verify=False,
            timeout=30,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {panel.api_token}",
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:

        try:
            response = await self._client.request(
                method,
                path,
                **kwargs,
            )

        except httpx.HTTPError as exc:
            raise SanaeiApiError(
                f"خطا در اتصال به پنل «{self.panel.name}»: {exc}"
            ) from exc

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {response.status_code}):\n"
                f"{response.text[:1000]}"
            )

        if response.status_code == 401:
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» ناموفق بود."
            )

        if response.status_code >= 400:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {response.status_code}): "
                f"{data.get('msg', data)}"
            )

        if not data.get("success", True):
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', 'خطای نامشخص')}"
            )

        return data

    # ==========================================================
    # INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:
        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/list",
        )

        obj = data.get("obj", [])

        if isinstance(obj, list):
            return obj

        return []

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
            traffic_gb * 1024 * 1024 * 1024
            if traffic_gb > 0
            else 0
        )

        sub_id = uuid.uuid4().hex[:16]

        client_obj = {
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
            "inboundId": inbound_id,
            "client": client_obj,
        }

        data = await self._request(
            "POST",
            f"{self.panel.api_base_path}/clients/add",
            json=payload,
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": sub_id,
            "inbound_id": inbound_id,
            "inbound": None,
            "response": data,
        }

    # ==========================================================
    # GET CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/clients/traffic/{quote(email, safe='')}",
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
            f"{self.panel.api_base_path}/clients/delete",
            json={
                "inboundId": inbound_id,
                "clientId": client_uuid,
            },
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close(self) -> None:
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
        .split("://")[-1]
        .split(":")[0]
        .split("/")[0]
    )

    port = inbound.get("port")

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

        if security == "tls":
            params.append(
                f"sni={host}"
            )

        if security == "reality":

            reality = stream_settings.get(
                "realitySettings",
                {},
            )

            server_names = reality.get(
                "serverNames",
                [],
            )

            if server_names:
                params.append(
                    "sni="
                    + quote(
                        server_names[0],
                        safe="",
                    )
                )

            fingerprint = reality.get(
                "settings",
                {},
            ).get(
                "fingerprint"
            )

            if fingerprint:
                params.append(
                    f"fp={quote(fingerprint, safe='')}"
                )

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
                "path="
                + quote(
                    path,
                    safe="",
                )
            )

            headers = ws_settings.get(
                "headers",
                {},
            )

            host_header = headers.get(
                "Host"
            )

            if host_header:
                params.append(
                    "host="
                    + quote(
                        host_header,
                        safe="",
                    )
                )

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
        "path": stream_settings.get(
            "wsSettings",
            {},
        ).get(
            "path",
            "",
        ),
        "tls": security,
    }

    raw = json.dumps(
        vmess_obj,
        separators=(",", ":"),
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )