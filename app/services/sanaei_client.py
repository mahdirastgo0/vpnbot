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
                "Authorization": f"Bearer {panel.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

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

        text = resp.text

        if resp.status_code == 404:
            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {resp.request.url}\n"
                f"HTTP: 404"
            )

        if resp.status_code == 401:
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد."
            )

        if resp.status_code >= 400:
            raise SanaeiApiError(
                f"خطای HTTP {resp.status_code} از پنل "
                f"«{self.panel.name}»:\n{text[:1000]}"
            )

        try:
            data = resp.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ JSON معتبر نیست:\n{text[:1000]}"
            )

        if not isinstance(data, dict):
            raise SanaeiApiError(
                f"فرمت پاسخ پنل نامعتبر است:\n{data}"
            )

        if data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', 'خطای نامشخص')}"
            )

        return data

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/list",
        )

        obj = data.get("obj") or []

        if isinstance(obj, dict):
            return obj.get("inbounds", [])

        return obj

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:

        # ------------------------------------------------------
        # نام کانفیگ = همان چیزی که کاربر وارد کرده
        # ------------------------------------------------------

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ خالی است."
            )

        inbound_id = (
            inbound_id
            if inbound_id is not None
            else self.panel.inbound_id
        )

        if not inbound_id:
            raise SanaeiApiError(
                "INBOUND_ID برای این پنل تنظیم نشده است."
            )

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

        # ------------------------------------------------------
        # مهم:
        #
        # API جدید پنل /clients/add یک Client را داخل
        # inbound دریافت می‌کند.
        #
        # tgId باید عدد باشد، نه string.
        # ------------------------------------------------------

        client = {
            "id": client_uuid,
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": 0,
            "subId": uuid.uuid4().hex[:16],
        }

        # ------------------------------------------------------
        # API پنل:
        #
        # POST /panel/api/clients/add
        #
        # حداقل یکی از inboundها باید داخل درخواست باشد.
        # ------------------------------------------------------

        payload = {
            "inbounds": [
                {
                    "id": inbound_id,
                    "client": client,
                }
            ]
        }

        data = await self._request(
            "POST",
            f"{self.panel.api_base_path}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # اطلاعات inbound را برای ساخت لینک بگیر
        # ------------------------------------------------------

        inbounds = await self.list_inbounds()

        inbound = next(
            (
                item
                for item in inbounds
                if int(item.get("id", 0)) == int(inbound_id)
            ),
            None,
        )

        if inbound is None:
            raise SanaeiApiError(
                f"اینباند شماره {inbound_id} روی پنل "
                f"«{self.panel.name}» پیدا نشد."
            )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound": inbound,
            "response": data,
        }

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/"
            f"getClientTraffics/{quote(email)}",
        )

        return data.get("obj")

    async def delete_client(
        self,
        inbound_id: int,
        client_uuid: str,
    ) -> None:

        await self._request(
            "POST",
            f"{self.panel.api_base_path}/inbounds/"
            f"{inbound_id}/delClient/{client_uuid}",
        )

    async def close(self) -> None:
        await self._client.aclose()


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

    host = panel.url.split("://")[-1].split(":")[0]

    port = inbound.get("port")

    remark = quote(
        f"{panel.name}-{email}"
    )

    # ----------------------------------------------------------
    # VLESS
    # ----------------------------------------------------------

    if panel.protocol.lower() == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        if security == "tls":
            params.append(
                "sni=" + quote(host)
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
                    "sni=" + quote(server_names[0])
                )

            short_ids = reality.get(
                "shortIds",
                [],
            )

            if short_ids:
                params.append(
                    "sid=" + quote(short_ids[0])
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
                "path=" + quote(
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
                    "host=" + quote(
                        host_header
                    )
                )

        if network == "grpc":

            grpc_settings = stream_settings.get(
                "grpcSettings",
                {},
            )

            service_name = grpc_settings.get(
                "serviceName",
                "",
            )

            if service_name:
                params.append(
                    "serviceName="
                    + quote(service_name)
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
        "tls": (
            "tls"
            if security in ("tls", "reality")
            else ""
        ),
    }

    raw = json.dumps(
        vmess_obj,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )