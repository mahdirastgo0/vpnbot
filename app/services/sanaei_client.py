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
            base_url=panel.url.rstrip("/"),
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

        response = await self._client.request(
            method,
            path,
            **kwargs,
        )

        text = response.text

        if response.status_code == 404:
            raise SanaeiApiError(
                "Endpoint پنل پیدا نشد.\n"
                f"URL: {response.request.url}\n"
                f"HTTP: {response.status_code}"
            )

        if response.status_code == 401:
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» رد شد.\n"
                "API Token را بررسی کن."
            )

        if response.status_code >= 400:
            raise SanaeiApiError(
                f"خطای HTTP {response.status_code} از پنل "
                f"«{self.panel.name}»:\n"
                f"{text[:2000]}"
            )

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                "پاسخ پنل JSON معتبر نیست:\n"
                f"{text[:2000]}"
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

    # ==========================================================
    # LIST INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}/inbounds/list",
        )

        obj = data.get("obj") or []

        if isinstance(obj, dict):

            if isinstance(obj.get("inbounds"), list):
                return obj["inbounds"]

            return []

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

        # ------------------------------------------------------
        # نام کانفیگ = دقیقاً نامی که کاربر وارد کرده
        # ------------------------------------------------------

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "client email is required"
            )

        # ------------------------------------------------------
        # inbound
        # ------------------------------------------------------

        inbound_id = (
            inbound_id
            if inbound_id is not None
            else self.panel.inbound_id
        )

        if not inbound_id:
            raise SanaeiApiError(
                "INBOUND_ID برای این پنل تنظیم نشده است."
            )

        inbound_id = int(inbound_id)

        # ------------------------------------------------------
        # UUID
        # ------------------------------------------------------

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # expiry
        #
        # اگر مدت 30 روز باشد:
        # current time + 30 days
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
        # حجم
        # ------------------------------------------------------

        if traffic_gb > 0:

            total_bytes = (
                traffic_gb
                * 1024
                * 1024
                * 1024
            )

        else:

            total_bytes = 0

        # ======================================================
        # CLIENT
        #
        # ساختار واقعی API پنل شما
        #
        # client:
        # {
        #   email,
        #   subId,
        #   id,
        #   enable,
        #   expiryTime,
        #   totalGB,
        #   limitIp,
        #   tgId
        # }
        #
        # auth/password را خود پنل تولید می‌کند.
        # ======================================================

        client = {
            "email": email,
            "subId": uuid.uuid4().hex[:16],
            "id": client_uuid,
            "enable": True,
            "expiryTime": expire_ms,
            "totalGB": total_bytes,
            "limitIp": 0,
            "tgId": 0,
        }

        # ======================================================
        # PAYLOAD واقعی API
        #
        # {
        #     "client": {...},
        #     "inboundIds": [2, 8]
        # }
        # ======================================================

        payload = {
            "client": client,
            "inboundIds": [
                inbound_id
            ],
        }

        # ------------------------------------------------------
        # POST /panel/api/clients/add
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            f"{self.panel.api_base_path}/clients/add",
            json=payload,
        )

        # ======================================================
        # پاسخ API ممکن است Client ساخته‌شده را برگرداند.
        # اگر UUID را پنل تغییر داده باشد، UUID واقعی را
        # از پاسخ می‌گیریم.
        # ======================================================

        response_client = data.get("client")

        if isinstance(response_client, dict):

            real_uuid = response_client.get("id")

            if real_uuid:
                client_uuid = str(real_uuid)

            real_email = response_client.get("email")

            if real_email:
                email = str(real_email)

        # ======================================================
        # دریافت inbound
        # ======================================================

        inbounds = await self.list_inbounds()

        inbound = next(
            (
                item
                for item in inbounds
                if int(item.get("id", 0))
                == inbound_id
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

    # ==========================================================
    # GET CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        email = (email or "").strip()

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}"
            f"/inbounds/getClientTraffics/"
            f"{quote(email)}",
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
    # CLOSE
    # ==========================================================

    async def close(self) -> None:

        await self._client.aclose()


# ==============================================================
# BUILD CONFIG LINK
# ==============================================================

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
    # HOST
    # ----------------------------------------------------------

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

        # ------------------------------------------------------
        # TLS
        # ------------------------------------------------------

        if security == "tls":

            params.append(
                "sni=" + quote(host)
            )

        # ------------------------------------------------------
        # REALITY
        # ------------------------------------------------------

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
                        str(server_names[0])
                    )
                )

            short_ids = reality.get(
                "shortIds",
                [],
            )

            if short_ids:

                params.append(
                    "sid="
                    + quote(
                        str(short_ids[0])
                    )
                )

        # ------------------------------------------------------
        # WebSocket
        # ------------------------------------------------------

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
                "path="
                + quote(
                    path,
                    safe="",
                )
            )

            headers = ws.get(
                "headers",
                {},
            )

            ws_host = headers.get(
                "Host"
            )

            if ws_host:

                params.append(
                    "host="
                    + quote(
                        str(ws_host)
                    )
                )

        # ------------------------------------------------------
        # gRPC
        # ------------------------------------------------------

        if network == "grpc":

            grpc = stream_settings.get(
                "grpcSettings",
                {},
            )

            service_name = grpc.get(
                "serviceName",
                "",
            )

            if service_name:

                params.append(
                    "serviceName="
                    + quote(
                        str(service_name)
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