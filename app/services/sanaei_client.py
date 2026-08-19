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
            base_url=panel.url,
            verify=False,
            timeout=20,
            follow_redirects=True,
        )

        self._logged_in = False

    # ======================================================
    # REQUEST
    # ======================================================

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

        # --------------------------------------------------
        # Session expired / unauthorized
        # --------------------------------------------------

        if response.status_code in (401, 403):

            self._logged_in = False

            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» نامعتبر یا منقضی شده است."
            )

        # --------------------------------------------------
        # 404
        # --------------------------------------------------

        if response.status_code == 404:

            raise SanaeiApiError(
                f"Endpoint پنل پیدا نشد:\n"
                f"{method} {path}\n"
                f"Base URL: {self.panel.url}"
            )

        # --------------------------------------------------
        # HTTP errors
        # --------------------------------------------------

        try:
            response.raise_for_status()

        except httpx.HTTPStatusError as exc:

            body = response.text[:1000]

            raise SanaeiApiError(
                f"خطای HTTP پنل:\n"
                f"{exc}\n"
                f"Response: {body}"
            ) from exc

        # --------------------------------------------------
        # JSON
        # --------------------------------------------------

        try:
            data = response.json()

        except Exception as exc:

            raise SanaeiApiError(
                f"پاسخ پنل JSON نیست.\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text[:1000]}"
            ) from exc

        # --------------------------------------------------
        # Panel success flag
        # --------------------------------------------------

        if isinstance(data, dict):

            if data.get("success") is False:

                raise SanaeiApiError(
                    f"خطای پنل «{self.panel.name}»: "
                    f"{data.get('msg', 'خطای نامشخص')}"
                )

        return data

    # ======================================================
    # LOGIN
    # ======================================================

    async def login(self) -> bool:

        try:

            data = await self._request(
                "POST",
                "/login",
                json={
                    "username": self.panel.username,
                    "password": self.panel.password,
                },
            )

        except SanaeiApiError:

            self._logged_in = False
            raise

        if not data.get("success"):

            self._logged_in = False

            raise SanaeiApiError(
                f"ورود به پنل «{self.panel.name}» ناموفق بود: "
                f"{data.get('msg', 'نام کاربری یا رمز عبور اشتباه است.')}"
            )

        self._logged_in = True

        return True

    # ======================================================
    # ENSURE LOGIN
    # ======================================================

    async def ensure_login(self) -> None:

        if self._logged_in:
            return

        await self.login()

    # ======================================================
    # API PATH
    # ======================================================

    def _api(
        self,
        path: str,
    ) -> str:

        base = self.panel.api_base_path.rstrip("/")

        path = path.lstrip("/")

        return f"{base}/{path}"

    # ======================================================
    # LIST INBOUNDS
    # ======================================================

    async def list_inbounds(self) -> list[dict]:

        await self.ensure_login()

        data = await self._request(
            "GET",
            self._api("inbounds/list"),
        )

        obj = data.get("obj")

        if obj is None:
            return []

        if isinstance(obj, list):
            return obj

        return []

    # ======================================================
    # GET INBOUND
    # ======================================================

    async def get_inbound(
        self,
        inbound_id: int,
    ) -> dict:

        await self.ensure_login()

        data = await self._request(
            "GET",
            self._api(
                f"inbounds/get/{inbound_id}"
            ),
        )

        obj = data.get("obj")

        if not obj:

            raise SanaeiApiError(
                f"اینباند {inbound_id} در پنل "
                f"«{self.panel.name}» پیدا نشد."
            )

        return obj

    # ======================================================
    # ADD CLIENT
    # ======================================================

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:

        await self.ensure_login()

        inbound_id = (
            inbound_id
            if inbound_id is not None
            else self.panel.inbound_id
        )

        # --------------------------------------------------
        # UUID
        # --------------------------------------------------

        client_uuid = str(
            uuid.uuid4()
        )

        # --------------------------------------------------
        # Expiry
        # --------------------------------------------------

        expire_ms = int(
            (
                datetime.now(timezone.utc)
                + timedelta(days=duration_days)
            ).timestamp()
            * 1000
        )

        # --------------------------------------------------
        # Traffic
        # --------------------------------------------------

        total_bytes = (
            traffic_gb
            * 1024
            * 1024
            * 1024
            if traffic_gb > 0
            else 0
        )

        # --------------------------------------------------
        # Client object
        # --------------------------------------------------

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

        # --------------------------------------------------
        # 3x-ui addClient
        # --------------------------------------------------

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
            self._api("inbounds/addClient"),
            json=payload,
        )

        # --------------------------------------------------
        # Get inbound after creation
        # --------------------------------------------------

        inbound = await self.get_inbound(
            inbound_id
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound_id": inbound_id,
            "inbound": inbound,
            "response": data,
        }

    # ======================================================
    # CLIENT TRAFFIC
    # ======================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        await self.ensure_login()

        data = await self._request(
            "GET",
            self._api(
                f"inbounds/getClientTraffics/{quote(email)}"
            ),
        )

        return data.get("obj")

    # ======================================================
    # DELETE CLIENT
    # ======================================================

    async def delete_client(
        self,
        inbound_id: int,
        client_uuid: str,
    ) -> None:

        await self.ensure_login()

        await self._request(
            "POST",
            self._api(
                f"inbounds/{inbound_id}/delClient/{client_uuid}"
            ),
        )

    # ======================================================
    # CLOSE
    # ======================================================

    async def close(self) -> None:

        await self._client.aclose()


# ==========================================================
# CONFIG LINK
# ==========================================================

def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    stream_settings = json.loads(
        inbound.get("streamSettings")
        or "{}"
    )

    network = stream_settings.get(
        "network",
        "tcp",
    )

    security = stream_settings.get(
        "security",
        "none",
    )

    # ------------------------------------------------------
    # Address
    # ------------------------------------------------------

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

    # ======================================================
    # VLESS
    # ======================================================

    if panel.protocol == "vless":

        params = [
            f"type={network}",
            f"security={security}",
        ]

        # --------------------------------------------------
        # TLS
        # --------------------------------------------------

        if security == "tls":

            params.append(
                "sni=" + quote(host)
            )

        # --------------------------------------------------
        # WS
        # --------------------------------------------------

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

            ws_host = headers.get(
                "Host"
            )

            if ws_host:
                params.append(
                    "host=" + quote(
                        ws_host
                    )
                )

        # --------------------------------------------------
        # Reality
        # --------------------------------------------------

        if security == "reality":

            reality = stream_settings.get(
                "realitySettings",
                {},
            )

            settings = reality.get(
                "settings",
                {},
            )

            pbk = settings.get(
                "publicKey"
            )

            sid = settings.get(
                "shortId"
            )

            sni = ""

            server_names = reality.get(
                "serverNames",
                [],
            )

            if server_names:
                sni = server_names[0]

            if pbk:
                params.append(
                    "pbk=" + quote(
                        pbk
                    )
                )

            if sid:
                params.append(
                    "sid=" + quote(
                        sid
                    )
                )

            if sni:
                params.append(
                    "sni=" + quote(
                        sni
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
            f"{query}"
            f"#{remark}"
        )

    # ======================================================
    # VMESS
    # ======================================================

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