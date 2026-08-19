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

        headers = {
            "Authorization": f"Bearer {panel.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=panel.url.rstrip("/"),
            verify=False,
            timeout=30,
            headers=headers,
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

        resp = await self._client.request(
            method,
            path,
            **kwargs,
        )

        try:
            data = resp.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {resp.status_code})"
            )

        if resp.status_code >= 400:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {resp.status_code}): "
                f"{data.get('msg') or data}"
            )

        if not isinstance(data, dict):
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}»."
            )

        if data.get("success") is False:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg') or 'خطای نامشخص'}"
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
            obj = obj.get("items") or []

        return obj

    # ==========================================================
    # GET INBOUND
    # ==========================================================

    async def get_inbound(
        self,
        inbound_id: int | None = None,
    ) -> dict:

        inbound_id = inbound_id or self.panel.inbound_id

        inbounds = await self.list_inbounds()

        for inbound in inbounds:

            try:
                if int(inbound.get("id")) == int(inbound_id):
                    return inbound
            except Exception:
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

        inbound_id = inbound_id or self.panel.inbound_id

        email = (email or "").strip()

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ / email نمی‌تواند خالی باشد."
            )

        client_uuid = str(uuid.uuid4())

        # ------------------------------------------------------
        # حجم
        # ------------------------------------------------------

        total_bytes = (
            traffic_gb * 1024 * 1024 * 1024
            if traffic_gb > 0
            else 0
        )

        # ------------------------------------------------------
        # زمان انقضا
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
        # Client
        #
        # نکته مهم:
        # tgId باید عدد باشد، نه string
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
        # طبق API پنل:
        #
        # POST /panel/api/clients/add
        #
        # inboundIds باید آرایه باشد.
        # ------------------------------------------------------

        payload = {
            "inboundIds": [
                int(inbound_id)
            ],
            "client": client,
        }

        data = await self._request(
            "POST",
            f"{self.panel.api_base_path}/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # اینباند اصلی را برای ساخت لینک می‌گیریم
        # ------------------------------------------------------

        inbound = await self.get_inbound(
            inbound_id
        )

        return {
            "client_uuid": client_uuid,
            "email": email,
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

        email = quote(
            email,
            safe="",
        )

        data = await self._request(
            "GET",
            f"{self.panel.api_base_path}"
            f"/inbounds/getClientTraffics/{email}",
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
            f"/inbounds/{inbound_id}/delClient/{client_uuid}",
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
    لینک کانفیگ را بر اساس تنظیمات واقعی خود INBOUND می‌سازد.

    نکته مهم:
    آدرس سرور از panel.url گرفته نمی‌شود.

    یعنی اگر پنل ایران باشد ولی اینباند مربوط به سرور
    لهستان با آدرس 45.80.108.236 باشد، لینک باید:

        45.80.108.236

    را استفاده کند.
    """

    # ----------------------------------------------------------
    # streamSettings
    # ----------------------------------------------------------

    raw_stream = inbound.get("streamSettings")

    if isinstance(raw_stream, str):
        try:
            stream_settings = json.loads(
                raw_stream or "{}"
            )
        except Exception:
            stream_settings = {}
    elif isinstance(raw_stream, dict):
        stream_settings = raw_stream
    else:
        stream_settings = {}

    # ----------------------------------------------------------
    # protocol
    # ----------------------------------------------------------

    protocol = (
        inbound.get("protocol")
        or panel.protocol
        or "vless"
    ).lower()

    # ----------------------------------------------------------
    # Port
    # ----------------------------------------------------------

    port = inbound.get("port")

    if not port:
        raise SanaeiApiError(
            "پورت اینباند پیدا نشد."
        )

    # ==========================================================
    # SERVER ADDRESS
    # ==========================================================
    #
    # اولویت:
    #
    # 1. serverName
    # 2. address
    # 3. host
    # 4. domain
    #
    # توجه:
    # panel.url عمداً اینجا استفاده نمی‌شود.
    #

    candidates = [
        inbound.get("serverName"),
        inbound.get("address"),
        inbound.get("host"),
        inbound.get("domain"),
    ]

    server = next(
        (
            str(x).strip()
            for x in candidates
            if x
        ),
        "",
    )

    # ----------------------------------------------------------
    # اگر در خود inbound نبود، از streamSettings پیدا کن
    # ----------------------------------------------------------

    if not server:

        candidates = [
            stream_settings.get("serverName"),
            stream_settings.get("address"),
            stream_settings.get("host"),
            stream_settings.get("domain"),
        ]

        server = next(
            (
                str(x).strip()
                for x in candidates
                if x
            ),
            "",
        )

    # ----------------------------------------------------------
    # اگر باز هم نبود، از TLS settings / Reality settings
    # ----------------------------------------------------------

    if not server:

        tls_settings = (
            stream_settings.get("tlsSettings")
            or {}
        )

        reality_settings = (
            stream_settings.get("realitySettings")
            or {}
        )

        candidates = [
            tls_settings.get("serverName"),
            tls_settings.get("address"),
            reality_settings.get("serverName"),
            reality_settings.get("address"),
        ]

        server = next(
            (
                str(x).strip()
                for x in candidates
                if x
            ),
            "",
        )

    # ----------------------------------------------------------
    # آخرین fallback
    #
    # این فقط برای جلوگیری از crash است.
    # در حالت درست باید server از inbound بیاید.
    # ----------------------------------------------------------

    if not server:

        raise SanaeiApiError(
            "آدرس سرور داخل تنظیمات اینباند پیدا نشد. "
            "فیلد address/serverName/host اینباند خالی است."
        )

    # ==========================================================
    # NETWORK
    # ==========================================================

    network = (
        stream_settings.get("network")
        or "tcp"
    ).lower()

    # ==========================================================
    # SECURITY
    # ==========================================================

    security = (
        stream_settings.get("security")
        or "none"
    ).lower()

    # ==========================================================
    # VLESS
    # ==========================================================

    if protocol == "vless":

        params: list[str] = []

        # ------------------------------------------------------
        # encryption
        #
        # در بعضی نسخه‌های پنل مقدار encryption داخل settings
        # کلاینت/اینباند ذخیره می‌شود.
        # ------------------------------------------------------

        client_settings = inbound.get(
            "clientSettings"
        )

        if isinstance(client_settings, str):
            try:
                client_settings = json.loads(
                    client_settings
                )
            except Exception:
                client_settings = {}

        if not isinstance(client_settings, dict):
            client_settings = {}

        encryption = (
            client_settings.get("encryption")
            or inbound.get("encryption")
            or "none"
        )

        params.append(
            "encryption=" + quote(
                str(encryption),
                safe="",
            )
        )

        # ------------------------------------------------------
        # security
        # ------------------------------------------------------

        params.append(
            "security=" + quote(
                security,
                safe="",
            )
        )

        # ======================================================
        # TLS
        # ======================================================

        if security == "tls":

            tls_settings = (
                stream_settings.get(
                    "tlsSettings"
                )
                or {}
            )

            server_name = (
                tls_settings.get("serverName")
                or tls_settings.get("serverNames")
                or server
            )

            if isinstance(server_name, list):
                server_name = (
                    server_name[0]
                    if server_name
                    else server
                )

            params.append(
                "sni=" + quote(
                    str(server_name),
                    safe="",
                )
            )

            # fingerprint

            fingerprint = (
                tls_settings.get("fingerprint")
                or tls_settings.get("fp")
            )

            if fingerprint:
                params.append(
                    "fp=" + quote(
                        str(fingerprint),
                        safe="",
                    )
                )

            # ALPN

            alpn = tls_settings.get("alpn")

            if alpn:

                if isinstance(alpn, list):
                    alpn = ",".join(
                        str(x)
                        for x in alpn
                    )

                params.append(
                    "alpn=" + quote(
                        str(alpn),
                        safe="",
                    )
                )

            # allow insecure

            if "allowInsecure" in tls_settings:

                allow_insecure = (
                    tls_settings.get(
                        "allowInsecure"
                    )
                )

                params.append(
                    "insecure="
                    + (
                        "1"
                        if allow_insecure
                        else "0"
                    )
                )

        # ======================================================
        # REALITY
        # ======================================================

        if security == "reality":

            reality = (
                stream_settings.get(
                    "realitySettings"
                )
                or {}
            )

            reality_settings = (
                reality.get("settings")
                or {}
            )

            # serverName

            server_names = (
                reality.get("serverNames")
                or reality.get("serverName")
                or []
            )

            if isinstance(
                server_names,
                str,
            ):
                server_names = [
                    server_names
                ]

            if server_names:

                params.append(
                    "sni=" + quote(
                        str(
                            server_names[0]
                        ),
                        safe="",
                    )
                )

            # fingerprint

            fingerprint = (
                reality_settings.get(
                    "fingerprint"
                )
                or reality.get("fingerprint")
            )

            if fingerprint:

                params.append(
                    "fp=" + quote(
                        str(fingerprint),
                        safe="",
                    )
                )

            # public key

            public_key = (
                reality_settings.get(
                    "publicKey"
                )
                or reality.get("publicKey")
            )

            if public_key:

                params.append(
                    "pbk=" + quote(
                        str(public_key),
                        safe="",
                    )
                )

            # short id

            short_id = (
                reality_settings.get(
                    "shortId"
                )
                or reality.get("shortId")
            )

            if short_id:

                params.append(
                    "sid=" + quote(
                        str(short_id),
                        safe="",
                    )
                )

            # spiderX

            spider_x = (
                reality_settings.get(
                    "spiderX"
                )
                or reality.get("spiderX")
            )

            if spider_x:

                params.append(
                    "spx=" + quote(
                        str(spider_x),
                        safe="",
                    )
                )

        # ======================================================
        # TRANSPORT
        # ======================================================

        params.append(
            "type=" + quote(
                network,
                safe="",
            )
        )

        # ------------------------------------------------------
        # WebSocket
        # ------------------------------------------------------

        if network == "ws":

            ws = (
                stream_settings.get(
                    "wsSettings"
                )
                or {}
            )

            path = (
                ws.get("path")
                or "/"
            )

            params.append(
                "path=" + quote(
                    str(path),
                    safe="",
                )
            )

            ws_headers = (
                ws.get("headers")
                or {}
            )

            ws_host = (
                ws_headers.get("Host")
                or ws_headers.get("host")
            )

            if ws_host:
                params.append(
                    "host=" + quote(
                        str(ws_host),
                        safe="",
                    )
                )

        # ------------------------------------------------------
        # gRPC
        # ------------------------------------------------------

        elif network == "grpc":

            grpc = (
                stream_settings.get(
                    "grpcSettings"
                )
                or {}
            )

            service_name = (
                grpc.get("serviceName")
                or ""
            )

            if service_name:

                params.append(
                    "serviceName="
                    + quote(
                        str(service_name),
                        safe="",
                    )
                )

        # ------------------------------------------------------
        # HTTP
        # ------------------------------------------------------

        elif network in (
            "http",
            "h2",
        ):

            http_settings = (
                stream_settings.get(
                    "httpSettings"
                )
                or {}
            )

            path = (
                http_settings.get("path")
                or "/"
            )

            params.append(
                "path=" + quote(
                    str(path),
                    safe="",
                )
            )

            hosts = (
                http_settings.get(
                    "host"
                )
                or []
            )

            if isinstance(
                hosts,
                str,
            ):
                hosts = [hosts]

            if hosts:

                params.append(
                    "host=" + quote(
                        str(hosts[0]),
                        safe="",
                    )
                )

        # ------------------------------------------------------
        # Final VLESS
        # ------------------------------------------------------

        query = "&".join(params)

        remark = quote(
            email,
            safe="",
        )

        return (
            f"vless://"
            f"{client_uuid}@"
            f"{server}:{port}"
            f"?{query}"
            f"#{remark}"
        )

    # ==========================================================
    # VMESS
    # ==========================================================

    if protocol == "vmess":

        ws = (
            stream_settings.get(
                "wsSettings"
            )
            or {}
        )

        path = (
            ws.get("path")
            or "/"
        )

        ws_headers = (
            ws.get("headers")
            or {}
        )

        ws_host = (
            ws_headers.get("Host")
            or ws_headers.get("host")
            or ""
        )

        vmess_obj = {
            "v": "2",
            "ps": email,
            "add": server,
            "port": str(port),
            "id": client_uuid,
            "aid": "0",
            "scy": "auto",
            "net": network,
            "type": "none",
            "host": ws_host,
            "path": path,
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

    raise SanaeiApiError(
        f"پروتکل «{protocol}» برای ساخت لینک "
        f"پشتیبانی نمی‌شود."
    )