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
            response = await self._client.request(
                method,
                path,
                **kwargs,
            )

        except httpx.RequestError as e:
            raise SanaeiApiError(
                f"ارتباط با پنل «{self.panel.name}» برقرار نشد:\n{e}"
            ) from e

        if response.status_code == 404:
            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد.\n"
                f"URL: {response.request.url}\n"
                f"HTTP: 404"
            )

        if response.status_code in (401, 403):
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» ناموفق بود.\n"
                f"HTTP: {response.status_code}"
            )

        if response.status_code >= 400:
            raise SanaeiApiError(
                f"خطای HTTP از پنل «{self.panel.name}»:\n"
                f"HTTP: {response.status_code}\n"
                f"{response.text[:1000]}"
            )

        try:
            data = response.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ JSON نامعتبر از پنل «{self.panel.name}»:\n"
                f"{response.text[:1000]}"
            )

        if isinstance(data, dict) and data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg') or data.get('message') or data}"
            )

        return data

    # ==========================================================
    # INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            "/panel/api/inbounds/list",
        )

        obj = data.get("obj", [])

        return obj if isinstance(obj, list) else []

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
    # Endpoint:
    # POST /panel/api/clients/add
    #
    # ساختار API:
    #
    # {
    #   "inbounds": [2],
    #   "client": {
    #       "email": "...",
    #       ...
    #   }
    # }
    #
    # email = نام کانفیگ انتخاب‌شده توسط کاربر
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
            int(inbound_id)
            if inbound_id is not None
            else int(self.panel.inbound_id)
        )

        # ------------------------------------------------------
        # نام کانفیگ
        # ------------------------------------------------------

        email = str(email).strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ خالی است."
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
        # ------------------------------------------------------

        total_bytes = (
            0
            if traffic_gb <= 0
            else int(traffic_gb)
            * 1024
            * 1024
            * 1024
        )

        # ------------------------------------------------------
        # Telegram ID
        # ------------------------------------------------------

        tg_id = (
            int(telegram_id)
            if telegram_id is not None
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
            "tgId": tg_id,
            "subId": uuid.uuid4().hex[:16],
        }

        # ------------------------------------------------------
        # Payload
        #
        # توجه:
        # inbounds باید آرایه‌ای از ID باشد.
        # client جداگانه ارسال می‌شود.
        # ------------------------------------------------------

        payload = {
            "inbounds": [
                inbound_id
            ],
            "client": client,
        }

        print()
        print("==========================================")
        print("SANAEI CREATE CLIENT")
        print("PANEL       :", self.panel.name)
        print("ENDPOINT    :", "/panel/api/clients/add")
        print("INBOUND     :", inbound_id)
        print("EMAIL       :", email)
        print("UUID        :", client_uuid)
        print("TRAFFIC GB  :", traffic_gb)
        print("TRAFFIC BYTE:", total_bytes)
        print("EXPIRY MS   :", expire_ms)
        print("TG ID       :", tg_id)
        print("==========================================")
        print()

        # ------------------------------------------------------
        # Create
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            "/panel/api/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # Get inbound
        # ------------------------------------------------------

        inbound = await self.get_inbound(
            inbound_id
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "sub_id": client["subId"],
            "inbound_id": inbound_id,
            "inbound": inbound,
            "response": data,
        }

    # ==========================================================
    # TRAFFIC
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
    # DELETE
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

    raw_stream = inbound.get(
        "streamSettings",
        "{}",
    )

    try:
        if isinstance(raw_stream, str):
            stream_settings = json.loads(
                raw_stream or "{}"
            )
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

    # ==========================================================
    # VLESS
    # ==========================================================

    if panel.protocol.lower() == "vless":

        params = [
            f"type={quote(str(network))}",
            f"security={quote(str(security))}",
        ]

        if security == "tls":

            tls = (
                stream_settings.get(
                    "tlsSettings",
                    {},
                )
                or {}
            )

            server_name = tls.get(
                "serverName"
            ) or host

            params.append(
                "sni=" + quote(str(server_name))
            )

        if network == "ws":

            ws = (
                stream_settings.get(
                    "wsSettings",
                    {},
                )
                or {}
            )

            path = ws.get(
                "path",
                "/",
            )

            headers = (
                ws.get(
                    "headers",
                    {},
                )
                or {}
            )

            params.append(
                "path="
                + quote(
                    str(path),
                    safe="",
                )
            )

            ws_host = headers.get("Host")

            if ws_host:
                params.append(
                    "host="
                    + quote(str(ws_host))
                )

        if security == "reality":

            reality = (
                stream_settings.get(
                    "realitySettings",
                    {},
                )
                or {}
            )

            reality_settings = (
                reality.get(
                    "settings",
                    {},
                )
                or {}
            )

            public_key = reality_settings.get(
                "publicKey",
                "",
            )

            fingerprint = reality_settings.get(
                "fingerprint",
                "chrome",
            )

            spider_x = reality_settings.get(
                "spiderX",
                "",
            )

            server_names = (
                reality.get(
                    "serverNames",
                    [],
                )
                or []
            )

            short_ids = (
                reality.get(
                    "shortIds",
                    [],
                )
                or []
            )

            if public_key:
                params.append(
                    "pbk="
                    + quote(str(public_key))
                )

            params.append(
                "fp="
                + quote(str(fingerprint))
            )

            if server_names:
                params.append(
                    "sni="
                    + quote(
                        str(server_names[0])
                    )
                )

            if short_ids:
                params.append(
                    "sid="
                    + quote(
                        str(short_ids[0])
                    )
                )

            if spider_x:
                params.append(
                    "spx="
                    + quote(
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

    vmess = {
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

        ws = (
            stream_settings.get(
                "wsSettings",
                {},
            )
            or {}
        )

        vmess["path"] = ws.get(
            "path",
            "/",
        )

        headers = (
            ws.get(
                "headers",
                {},
            )
            or {}
        )

        vmess["host"] = headers.get(
            "Host",
            "",
        )

    if security == "tls":
        vmess["tls"] = "tls"

    raw = json.dumps(
        vmess,
        separators=(",", ":"),
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )