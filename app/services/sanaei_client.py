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
            timeout=20,
            headers={
                "Authorization": f"Bearer {panel.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

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
        except httpx.HTTPError as e:
            raise SanaeiApiError(
                f"خطا در اتصال به پنل «{self.panel.name}»: {e}"
            ) from e

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

        try:
            data = resp.json()
        except Exception:
            raise SanaeiApiError(
                f"پاسخ نامعتبر از پنل «{self.panel.name}» "
                f"(HTTP {resp.status_code})"
            )

        if resp.status_code >= 400:
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', data)}"
            )

        if not data.get("success", True):
            raise SanaeiApiError(
                f"خطای پنل «{self.panel.name}»: "
                f"{data.get('msg', data)}"
            )

        return data

    async def list_inbounds(self) -> list[dict]:

        data = await self._request(
            "GET",
            "/panel/api/inbounds/list",
        )

        return data.get("obj") or []

    async def add_client(
        self,
        email: str,
        traffic_gb: int,
        duration_days: int,
        inbound_id: int | None = None,
    ) -> dict:

        inbound_id = inbound_id or self.panel.inbound_id

        if not email:
            raise SanaeiApiError(
                "نام کانفیگ/ایمیل خالی است."
            )

        # ------------------------------------------------------
        # UUID کلاینت
        # ------------------------------------------------------

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
        # تاریخ انقضا
        # ------------------------------------------------------

        expire_ms = int(
            (
                datetime.now(timezone.utc)
                + timedelta(days=duration_days)
            ).timestamp()
            * 1000
        )

        # ------------------------------------------------------
        # کلاینت
        #
        # مهم:
        # tgId باید عدد باشد.
        # ------------------------------------------------------

        client = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "limitIp": 0,
            "tgId": 0,
            "subId": uuid.uuid4().hex[:16],
        }

        # ------------------------------------------------------
        # Endpoint واقعی پنل شما:
        #
        # /panel/api/clients/add
        #
        # و inboundIds باید آرایه باشد.
        # ------------------------------------------------------

        payload = {
            "inboundIds": [inbound_id],
            "client": client,
        }

        await self._request(
            "POST",
            "/panel/api/clients/add",
            json=payload,
        )

        # ------------------------------------------------------
        # دوباره Inbound را می‌گیریم تا مشخصات واقعی
        # اتصال را از خود پنل بخوانیم.
        # ------------------------------------------------------

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
                f"اینباند {inbound_id} روی پنل "
                f"«{self.panel.name}» پیدا نشد."
            )

        return {
            "client_uuid": client_uuid,
            "email": email,
            "inbound": inbound,
        }

    async def get_client_traffic(
        self,
        email: str,
    ) -> dict | None:

        data = await self._request(
            "GET",
            f"/panel/api/inbounds/getClientTraffics/{quote(email)}",
        )

        return data.get("obj")

    async def delete_client(
        self,
        inbound_id: int,
        client_uuid: str,
    ) -> None:

        await self._request(
            "POST",
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
        )

    async def close(self) -> None:
        await self._client.aclose()


# ==============================================================
# HELPERS
# ==============================================================

def _json(value, default=None):
    if value is None:
        return default

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default

    return default


def _first(value, default=""):
    if value is None:
        return default

    if isinstance(value, list):
        return value[0] if value else default

    return value


# ==============================================================
# BUILD VLESS LINK
# ==============================================================

def build_config_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    """
    لینک VLESS را فقط بر اساس تنظیمات واقعی Inbound می‌سازد.

    نکته مهم:
    panel.url در این تابع اصلاً برای آدرس سرور استفاده نمی‌شود.
    """

    # ----------------------------------------------------------
    # streamSettings
    # ----------------------------------------------------------

    stream = _json(
        inbound.get("streamSettings"),
        {},
    )

    network = stream.get(
        "network",
        "tcp",
    )

    security = stream.get(
        "security",
        "none",
    )

    # ----------------------------------------------------------
    # آدرس واقعی سرور
    #
    # اول از listen/serverName/address داخل خود inbound.
    # اگر نبود، از settings.
    # اگر هیچ‌کدام نبود، مقدار address تعریف‌شده در panel.
    # ----------------------------------------------------------

    settings_obj = _json(
        inbound.get("settings"),
        {},
    )

    address = panel.server_address

    if not address:
        raise SanaeiApiError(
            f"آدرس واقعی سرور برای اینباند {inbound.get('id')} "
            f"از اطلاعات پنل پیدا نشد."
        )

    port = inbound.get("port")

    if not port:
        raise SanaeiApiError(
            f"پورت اینباند {inbound.get('id')} پیدا نشد."
        )

    # ----------------------------------------------------------
    # query parameters
    # ----------------------------------------------------------

    params: list[str] = []

    params.append(
        f"encryption={quote('none')}"
    )

    # ----------------------------------------------------------
    # security
    # ----------------------------------------------------------

    if security:
        params.append(
            f"security={quote(str(security))}"
        )

    # ----------------------------------------------------------
    # TLS
    # ----------------------------------------------------------

    tls = stream.get(
        "tlsSettings",
        {},
    ) or {}

    if isinstance(tls, str):
        tls = _json(tls, {})

    server_name = (
        tls.get("serverName")
        or tls.get("serverNames", [None])[0]
        or ""
    )

    fingerprint = (
        tls.get("fingerprint")
        or ""
    )

    alpn = tls.get(
        "alpn",
        [],
    )

    if isinstance(alpn, list):
        alpn_value = ",".join(
            str(x) for x in alpn
        )
    else:
        alpn_value = str(alpn or "")

    if server_name:
        params.append(
            f"sni={quote(str(server_name), safe='')}"
        )

    if fingerprint:
        params.append(
            f"fp={quote(str(fingerprint), safe='')}"
        )

    if alpn_value:
        params.append(
            f"alpn={quote(alpn_value, safe='')}"
        )

    # ----------------------------------------------------------
    # REALITY
    # ----------------------------------------------------------

    reality = tls.get(
        "realitySettings",
        {},
    ) or {}

    if reality:

        reality_fingerprint = (
            reality.get("fingerprint")
            or fingerprint
        )

        if reality_fingerprint:
            params.append(
                f"fp={quote(str(reality_fingerprint), safe='')}"
            )

        public_key = (
            reality.get("publicKey")
            or ""
        )

        short_id = (
            reality.get("shortId")
            or ""
        )

        spider_x = (
            reality.get("spiderX")
            or ""
        )

        if public_key:
            params.append(
                f"pbk={quote(str(public_key), safe='')}"
            )

        if short_id:
            params.append(
                f"sid={quote(str(short_id), safe='')}"
            )

        if spider_x:
            params.append(
                f"spx={quote(str(spider_x), safe='')}"
            )

    # ----------------------------------------------------------
    # WebSocket
    # ----------------------------------------------------------

    if network == "ws":

        ws = stream.get(
            "wsSettings",
            {},
        ) or {}

        path = ws.get(
            "path",
            "/",
        )

        headers = ws.get(
            "headers",
            {},
        ) or {}

        host = (
            headers.get("Host")
            or headers.get("host")
            or ""
        )

        params.append(
            "type=ws"
        )

        if host:
            params.append(
                f"host={quote(str(host), safe='')}"
            )

        params.append(
            f"path={quote(str(path), safe='')}"
        )

    # ----------------------------------------------------------
    # TCP
    # ----------------------------------------------------------

    elif network == "tcp":

        params.append(
            "type=tcp"
        )

    # ----------------------------------------------------------
    # gRPC
    # ----------------------------------------------------------

    elif network == "grpc":

        grpc = stream.get(
            "grpcSettings",
            {},
        ) or {}

        service_name = grpc.get(
            "serviceName",
            "",
        )

        params.append(
            "type=grpc"
        )

        if service_name:
            params.append(
                f"serviceName={quote(str(service_name), safe='')}"
            )

    # ----------------------------------------------------------
    # HTTP / XHTTP / سایر network ها
    # ----------------------------------------------------------

    else:

        params.append(
            f"type={quote(str(network), safe='')}"
        )

    # ----------------------------------------------------------
    # insecure
    # ----------------------------------------------------------

    if security == "tls":

        allow_insecure = tls.get(
            "allowInsecure",
            False,
        )

        params.append(
            "insecure=1"
            if allow_insecure
            else
            "insecure=0"
        )

        params.append(
            "allowInsecure=1"
            if allow_insecure
            else
            "allowInsecure=0"
        )

    # ----------------------------------------------------------
    # fragment
    # ----------------------------------------------------------

    remark = quote(
        f"{panel.name}-{email}",
        safe="",
    )

    query = "&".join(params)

    return (
        f"vless://{client_uuid}"
        f"@{address}:{port}"
        f"?{query}"
        f"#{remark}"
    )


# ==============================================================
# VMESS
# ==============================================================

def build_vmess_link(
    panel: PanelConfig,
    inbound: dict,
    client_uuid: str,
    email: str,
) -> str:

    stream = _json(
        inbound.get("streamSettings"),
        {},
    )

    network = stream.get(
        "network",
        "tcp",
    )

    security = stream.get(
        "security",
        "none",
    )

    settings_obj = _json(
        inbound.get("settings"),
        {},
    )

    address = (
        inbound.get("address")
        or inbound.get("server")
        or settings_obj.get("address")
        or getattr(panel, "server_address", "")
    )

    port = inbound.get("port")

    if not address or not port:
        raise SanaeiApiError(
            "آدرس یا پورت واقعی Inbound پیدا نشد."
        )

    ws = stream.get(
        "wsSettings",
        {},
    ) or {}

    headers = ws.get(
        "headers",
        {},
    ) or {}

    host = (
        headers.get("Host")
        or headers.get("host")
        or ""
    )

    path = ws.get(
        "path",
        "",
    )

    obj = {
        "v": "2",
        "ps": f"{panel.name}-{email}",
        "add": address,
        "port": str(port),
        "id": client_uuid,
        "aid": "0",
        "scy": "auto",
        "net": network,
        "type": "none",
        "host": host,
        "path": path,
        "tls": "tls" if security == "tls" else "",
        "sni": "",
    }

    tls = stream.get(
        "tlsSettings",
        {},
    ) or {}

    if tls:
        obj["sni"] = (
            tls.get("serverName")
            or ""
        )

    raw = json.dumps(
        obj,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()

    return (
        "vmess://"
        + base64.b64encode(raw).decode()
    )