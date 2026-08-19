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

        try:

            resp = await self._client.request(
                method,
                path,
                **kwargs,
            )

        except httpx.RequestError as e:

            raise SanaeiApiError(
                f"ارتباط با پنل «{self.panel.name}» برقرار نشد: {e}"
            ) from e

        # ------------------------------------------------------
        # 404
        # ------------------------------------------------------

        if resp.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {resp.request.url}\n"
                f"HTTP: 404"
            )

        # ------------------------------------------------------
        # Auth
        # ------------------------------------------------------

        if resp.status_code in (401, 403):

            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» ناموفق بود.\n"
                f"HTTP: {resp.status_code}"
            )

        # ------------------------------------------------------
        # سایر HTTP errorها
        # ------------------------------------------------------

        if resp.status_code >= 400:

            text = resp.text[:1000]

            raise SanaeiApiError(
                f"خطای HTTP از پنل «{self.panel.name}»:\n"
                f"HTTP: {resp.status_code}\n"
                f"{text}"
            )

        # ------------------------------------------------------
        # JSON
        # ------------------------------------------------------

        try:
            data = resp.json()

        except Exception as e:

            raise SanaeiApiError(
                f"پاسخ JSON نامعتبر از پنل «{self.panel.name}»:\n"
                f"{resp.text[:1000]}"
            ) from e

        # ------------------------------------------------------
        # API success
        # ------------------------------------------------------

        if isinstance(data, dict):

            if data.get("success") is False:

                raise SanaeiApiError(
                    f"خطای پنل «{self.panel.name}»: "
                    f"{data.get('msg') or data.get('message') or data}"
                )

        return data

    # ==========================================================
    # LIST INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            "/panel/api/inbounds/list",
        )

        obj = data.get("obj", [])

        if not isinstance(obj, list):
            return []

        return obj

    # ==========================================================
    # GET INBOUND
    # ==========================================================

    async def get_inbound(
        self,
        inbound_id: int,
    ) -> dict:

        inbounds = await self.list_inbounds()

        for inbound in inbounds:

            try:
                if int(inbound.get("id")) == int(inbound_id):
                    return inbound
            except Exception:
                continue

        raise SanaeiApiError(
            f"اینباند شماره {inbound_id} روی پنل "
            f"«{self.panel.name}» پیدا نشد."
        )

    # ==========================================================
    # ADD CLIENT
    #
    # Endpoint واقعی پنل:
    #
    # POST /panel/api/clients/add
    #
    # ساختار:
    #
    # {
    #   "inboundId": 2,
    #   "client": {
    #       ...
    #   }
    # }
    #
    # tgId باید INTEGER باشد.
    # ==========================================================

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
        telegram_id: int | None = None,
    ) -> dict:

        inbound_id = (
            inbound_id
            if inbound_id is not None
            else self.panel.inbound_id
        )

        # ------------------------------------------------------
        # UUID
        # ------------------------------------------------------

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # Expiry
        # ------------------------------------------------------

        expire_ms = int(
            (
                datetime.now(timezone.utc)
                + timedelta(days=duration_days)
            ).timestamp()
            * 1000
        )

        # ------------------------------------------------------
        # Traffic
        #
        # 0 = Unlimited
        # ------------------------------------------------------

        if traffic_gb <= 0:
            total_bytes = 0
        else:
            total_bytes = (
                int(traffic_gb)
                * 1024
                * 1024
                * 1024
            )

        # ------------------------------------------------------
        # Telegram ID
        #
        # پنل انتظار int64 دارد.
        # اگر Telegram ID نداریم، صفر می‌فرستیم.
        # ------------------------------------------------------

        tg_id = (
            int(telegram_id)
            if telegram_id is not None
            else 0
        )

        # ------------------------------------------------------
        # Subscription ID
        # ------------------------------------------------------

        sub_id = uuid.uuid4().hex[:16]

        # ------------------------------------------------------
        # Client
        # ------------------------------------------------------

        client = {
            "id": client_uuid,
            "flow": "",
            "email": str(email),

            "limitIp": 0,

            "totalGB": total_bytes,

            "expiryTime": expire_ms,

            "enable": True,

            # بسیار مهم:
            # int، نه string
            "tgId": tg_id,

            "subId": sub_id,
        }

        # ------------------------------------------------------
        # Payload واقعی endpoint clients/add
        # ------------------------------------------------------

        payload = {
            "inboundId": int(inbound_id),
            "client": client,
        }

        # ------------------------------------------------------
        # Debug
        # ------------------------------------------------------

        print()
        print("========== SANAEI CREATE CLIENT ==========")
        print("PANEL       :", self.panel.name)
        print("ENDPOINT    :", "/panel/api/clients/add")
        print("INBOUND     :", inbound_id)
        print("EMAIL       :", email)
        print("UUID        :", client_uuid)
        print("TRAFFIC GB  :", traffic_gb)
        print("TRAFFIC BYTES:", total_bytes)
        print("EXPIRY MS   :", expire_ms)
        print("TG ID       :", tg_id)
        print("SUB ID      :", sub_id)
        print("==========================================")
        print()

        # ------------------------------------------------------
        # API call
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            "/panel/api/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # Get inbound after creation
        # ------------------------------------------------------

        inbound = await self.get_inbound(
            int(inbound_id)
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": sub_id,
            "inbound_id": int(inbound_id),
            "inbound": inbound,
            "response": data,
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
            f"/panel/api/inbounds/getClientTraffics/{quote(email)}",
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
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
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

    # ----------------------------------------------------------
    # Stream settings
    # ----------------------------------------------------------

    raw_stream = inbound.get(
        "streamSettings",
        "{}",
    )

    try:

        if isinstance(raw_stream, str):
            stream_settings = json.loads(raw_stream or "{}")
        else:
            stream_settings = raw_stream or {}

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
    # Address
    # ----------------------------------------------------------

    host = (
        panel.url
        .split("://")[-1]
        .split("/")[0]
        .split(":")[0]
    )

    port = inbound.get("port")

    if not port:
        raise SanaeiApiError(
            "پورت اینباند از پنل دریافت نشد."
        )

    # ----------------------------------------------------------
    # VLESS
    # ----------------------------------------------------------

    if panel.protocol.lower() == "vless":

        params = [
            f"type={quote(str(network))}",
            f"security={quote(str(security))}",
        ]

        # ------------------------------------------------------
        # TLS
        # ------------------------------------------------------

        if security == "tls":

            params.append(
                "sni=" + quote(host)
            )

            tls_settings = (
                stream_settings.get(
                    "tlsSettings",
                    {},
                )
                or {}
            )

            server_name = tls_settings.get(
                "serverName"
            )

            if server_name:
                params.append(
                    "sni=" + quote(str(server_name))
                )

        # ------------------------------------------------------
        # WS
        # ------------------------------------------------------

        if network == "ws":

            ws_settings = (
                stream_settings.get(
                    "wsSettings",
                    {},
                )
                or {}
            )

            path = ws_settings.get(
                "path",
                "/",
            )

            headers = ws_settings.get(
                "headers",
                {},
            ) or {}

            params.append(
                "path=" + quote(
                    str(path),
                    safe="",
                )
            )

            host_header = headers.get("Host")

            if host_header:
                params.append(
                    "host=" + quote(
                        str(host_header),
                    )
                )

        # ------------------------------------------------------
        # Reality
        # ------------------------------------------------------

        if security == "reality":

            reality = (
                stream_settings.get(
                    "realitySettings",
                    {},
                )
                or {}
            )

            settings_obj = (
                reality.get(
                    "settings",
                    {},
                )
                or {}
            )

            server_names = (
                reality.get(
                    "serverNames",
                    [],
                )
                or []
            )

            public_key = (
                settings_obj.get(
                    "publicKey",
                    "",
                )
            )

            fingerprint = (
                settings_obj.get(
                    "fingerprint",
                    "chrome",
                )
            )

            spider_x = (
                settings_obj.get(
                    "spiderX",
                    "",
                )
            )

            short_ids = (
                reality.get(
                    "shortIds",
                    [],
                )
                or []
            )

            params.append(
                "pbk=" + quote(
                    str(public_key)
                )
            )

            params.append(
                "fp=" + quote(
                    str(fingerprint)
                )
            )

            if server_names:
                params.append(
                    "sni=" + quote(
                        str(server_names[0])
                    )
                )

            if short_ids:
                params.append(
                    "sid=" + quote(
                        str(short_ids[0])
                    )
                )

            if spider_x:
                params.append(
                    "spx=" + quote(
                        str(spider_x),
                        safe="",
                    )
                )

        query = "&".join(params)

        remark = quote(
            f"{panel.name}-{email}"
        )

        return (
            f"vless://"
            f"{client_uuid}"
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

    # ----------------------------------------------------------
    # WS
    # ----------------------------------------------------------

    if network == "ws":

        ws_settings = (
            stream_settings.get(
                "wsSettings",
                {},
            )
            or {}
        )

        vmess_obj["path"] = ws_settings.get(
            "path",
            "/",
        )

        headers = ws_settings.get(
            "headers",
            {},
        ) or {}

        vmess_obj["host"] = headers.get(
            "Host",
            "",
        )

    # ----------------------------------------------------------
    # Security
    # ----------------------------------------------------------

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