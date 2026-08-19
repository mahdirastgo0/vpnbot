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
    """
    Client for the Sanaei/3x-ui API used by this project.

    Authentication:
        Authorization: Bearer <API_TOKEN>

    Client creation:
        POST /panel/api/clients/add

    Important:
        - inbound is selected by inbound_id
        - email is the client/config name
        - totalGB and expiryTime belong to the client
        - tgId must be an integer (0)
    """

    def __init__(self, panel: PanelConfig):
        self.panel = panel

        api_base_path = getattr(
            panel,
            "api_base_path",
            "/panel/api",
        ).strip()

        if not api_base_path.startswith("/"):
            api_base_path = "/" + api_base_path

        api_base_path = api_base_path.rstrip("/")

        self.api_base_path = api_base_path

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

        if not path.startswith("/"):
            path = "/" + path

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

        # ------------------------------------------------------
        # Endpoint not found
        # ------------------------------------------------------

        if response.status_code == 404:
            raise SanaeiApiError(
                "Endpoint پنل پیدا نشد.\n"
                f"URL: {self.panel.url}{path}\n"
                f"HTTP: {response.status_code}"
            )

        # ------------------------------------------------------
        # Authentication
        # ------------------------------------------------------

        if response.status_code in (401, 403):
            raise SanaeiApiError(
                f"احراز هویت پنل «{self.panel.name}» ناموفق بود.\n"
                "API Token را در panel.env بررسی کن."
            )

        # ------------------------------------------------------
        # Other HTTP errors
        # ------------------------------------------------------

        if response.status_code >= 400:
            body = response.text[:1000]

            raise SanaeiApiError(
                f"خطای HTTP پنل «{self.panel.name}»:\n"
                f"HTTP {response.status_code}\n"
                f"{body}"
            )

        # ------------------------------------------------------
        # JSON
        # ------------------------------------------------------

        try:
            data = response.json()
        except Exception as exc:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {response.status_code})"
            ) from exc

        if not isinstance(data, dict):
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}»."
            )

        # ------------------------------------------------------
        # Panel-level error
        # ------------------------------------------------------

        if data.get("success") is False:
            msg = data.get("msg") or "خطای نامشخص"

            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: {msg}"
            )

        return data

    # ==========================================================
    # LIST INBOUNDS
    # ==========================================================

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            f"{self.api_base_path}/inbounds/list",
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
        inbound_id: int,
    ) -> dict:

        # First try the normal endpoint.
        try:
            data = await self._request(
                "GET",
                f"{self.api_base_path}/inbounds/get/{inbound_id}",
            )

            obj = data.get("obj")

            if isinstance(obj, dict):
                return obj

        except SanaeiApiError:
            pass

        # Fallback: find it in the inbound list.
        inbounds = await self.list_inbounds()

        for inbound in inbounds:
            try:
                if int(inbound.get("id")) == int(inbound_id):
                    return inbound
            except (TypeError, ValueError):
                continue

        raise SanaeiApiError(
            f"اینباند شماره {inbound_id} "
            f"روی پنل «{self.panel.name}» پیدا نشد."
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
            if inbound_id is not None
            else self.panel.inbound_id
        )

        # ------------------------------------------------------
        # Client name / email
        # ------------------------------------------------------

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ / email نمی‌تواند خالی باشد."
            )

        # ------------------------------------------------------
        # UUID generated by us.
        # ------------------------------------------------------

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # Subscription ID
        # ------------------------------------------------------

        sub_id = uuid.uuid4().hex[:16]

        # ------------------------------------------------------
        # Traffic
        #
        # 0 = unlimited
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
        # Expiration
        #
        # 0 = unlimited
        # ------------------------------------------------------

        if duration_days <= 0:
            expire_ms = 0
        else:
            expire_ms = int(
                (
                    datetime.now(timezone.utc)
                    + timedelta(days=int(duration_days))
                ).timestamp()
                * 1000
            )

        # ------------------------------------------------------
        # IMPORTANT
        #
        # Based on the actual panel payload:
        #
        # client:
        # {
        #   email,
        #   subId,
        #   id,
        #   enable,
        #   expiryTime,
        #   limitIp,
        #   tgId,
        #   totalGB
        # }
        #
        # inboundIds:
        # [
        #   2,
        #   8
        # ]
        #
        # tgId MUST be integer 0.
        # ------------------------------------------------------

        client_obj = {
            "email": email,
            "subId": sub_id,
            "id": client_uuid,
            "enable": True,
            "expiryTime": expire_ms,
            "limitIp": 0,
            "tgId": 0,
            "totalGB": total_bytes,
        }

        payload = {
            "client": client_obj,
            "inboundIds": [
                int(inbound_id)
            ],
        }

        # ------------------------------------------------------
        # CREATE CLIENT
        # ------------------------------------------------------

        data = await self._request(
            "POST",
            f"{self.api_base_path}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # Get inbound after successful creation.
        #
        # We need stream settings / port for building
        # the client link.
        # ------------------------------------------------------

        inbound = await self.get_inbound(
            int(inbound_id)
        )

        return {
            "client_uuid": client_uuid,
            "sub_id": sub_id,
            "email": email,
            "inbound_id": int(inbound_id),
            "traffic_gb": traffic_gb,
            "duration_days": duration_days,
            "expiry_ms": expire_ms,
            "total_bytes": total_bytes,
            "response": data,
            "inbound": inbound,
        }

    # ==========================================================
    # CLIENT TRAFFIC
    # ==========================================================

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        email = quote(
            (email or "").strip(),
            safe="",
        )

        data = await self._request(
            "GET",
            f"{self.api_base_path}/inbounds/getClientTraffics/{email}",
        )

        obj = data.get("obj")

        if isinstance(obj, dict):
            return obj

        return None

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
            f"{self.api_base_path}/inbounds/"
            f"{int(inbound_id)}/delClient/{client_uuid}",
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

    """
    Builds VLESS/VMess link from the selected inbound.

    IMPORTANT:
    The VPN server address should NOT blindly be taken from
    panel.url.

    If the PanelConfig has a dedicated server_host/server_ip,
    use that.

    Otherwise, fall back to panel.url hostname.
    """

    # ----------------------------------------------------------
    # Stream settings
    # ----------------------------------------------------------

    raw_stream = inbound.get("streamSettings") or "{}"

    if isinstance(raw_stream, str):

        try:
            stream_settings = json.loads(raw_stream)
        except Exception:
            stream_settings = {}

    elif isinstance(raw_stream, dict):
        stream_settings = raw_stream

    else:
        stream_settings = {}

    # ----------------------------------------------------------
    # Protocol
    # ----------------------------------------------------------

    protocol = (
        getattr(panel, "protocol", "vless")
        or "vless"
    ).lower()

    # ----------------------------------------------------------
    # Network
    # ----------------------------------------------------------

    network = stream_settings.get(
        "network",
        "tcp",
    )

    # ----------------------------------------------------------
    # Security
    # ----------------------------------------------------------

    security = stream_settings.get(
        "security",
        "none",
    )

    # ----------------------------------------------------------
    # Server address
    #
    # Prefer server_host/server_ip if they exist in PanelConfig.
    # This is important because the panel URL may point to Iran
    # while the actual VPN server is Poland.
    # ----------------------------------------------------------

    server_host = getattr(
        panel,
        "server_host",
        "",
    )

    if not server_host:
        server_host = getattr(
            panel,
            "server_ip",
            "",
        )

    if not server_host:

        panel_url = panel.url

        if "://" in panel_url:
            server_host = (
                panel_url
                .split("://", 1)[1]
                .split("/", 1)[0]
                .split(":", 1)[0]
            )
        else:
            server_host = (
                panel_url
                .split("/", 1)[0]
                .split(":", 1)[0]
            )

    # ----------------------------------------------------------
    # Port
    # ----------------------------------------------------------

    port = inbound.get("port")

    if port is None:
        raise SanaeiApiError(
            f"پورت اینباند برای پنل «{panel.name}» پیدا نشد."
        )

    # ----------------------------------------------------------
    # Remark
    # ----------------------------------------------------------

    remark = quote(
        f"{panel.name}-{email}",
        safe="",
    )

    # ==========================================================
    # VLESS
    # ==========================================================

    if protocol == "vless":

        params = [
            f"type={quote(str(network))}",
            f"security={quote(str(security))}",
        ]

        # ------------------------------------------------------
        # TLS
        # ------------------------------------------------------

        if security == "tls":

            tls_settings = (
                stream_settings.get(
                    "tlsSettings",
                    {},
                )
                or {}
            )

            sni = (
                tls_settings.get("serverName")
                or tls_settings.get("serverNames", [None])[0]
                or server_host
            )

            params.append(
                "sni=" + quote(str(sni))
            )

        # ------------------------------------------------------
        # Reality
        # ------------------------------------------------------

        elif security == "reality":

            reality_settings = (
                stream_settings.get(
                    "realitySettings",
                    {},
                )
                or {}
            )

            settings_obj = (
                reality_settings.get(
                    "settings",
                    {},
                )
                or {}
            )

            pbk = (
                settings_obj.get("publicKey")
                or reality_settings.get("publicKey")
            )

            sid = (
                settings_obj.get("shortId")
                or reality_settings.get("shortId")
                or ""
            )

            fp = (
                settings_obj.get("fingerprint")
                or "chrome"
            )

            sni = (
                reality_settings.get("serverName")
                or reality_settings.get("serverNames", [None])[0]
                or server_host
            )

            if pbk:
                params.append(
                    "pbk=" + quote(str(pbk))
                )

            if sid:
                params.append(
                    "sid=" + quote(str(sid))
                )

            params.append(
                "fp=" + quote(str(fp))
            )

            if sni:
                params.append(
                    "sni=" + quote(str(sni))
                )

        # ------------------------------------------------------
        # WebSocket
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

            host = (
                headers.get("Host")
                or headers.get("host")
            )

            params.append(
                "path=" + quote(
                    str(path),
                    safe="/",
                )
            )

            if host:
                params.append(
                    "host=" + quote(str(host))
                )

        # ------------------------------------------------------
        # gRPC
        # ------------------------------------------------------

        if network == "grpc":

            grpc_settings = (
                stream_settings.get(
                    "grpcSettings",
                    {},
                )
                or {}
            )

            service_name = grpc_settings.get(
                "serviceName",
                "",
            )

            if service_name:
                params.append(
                    "serviceName="
                    + quote(str(service_name))
                )

        query = "&".join(params)

        return (
            f"vless://{client_uuid}"
            f"@{server_host}:{port}"
            f"?{query}"
            f"#{remark}"
        )

    # ==========================================================
    # VMESS
    # ==========================================================

    vmess_obj = {
        "v": "2",
        "ps": f"{panel.name}-{email}",
        "add": server_host,
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

        vmess_obj["host"] = (
            headers.get("Host")
            or headers.get("host")
            or ""
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