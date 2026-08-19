from __future__ import annotations

import httpx

from app.config import settings

_BASE = "https://sandbox.zarinpal.com/pg/v4" if settings.ZARINPAL_SANDBOX else "https://api.zarinpal.com/pg/v4"
_STARTPAY_BASE = "https://sandbox.zarinpal.com/pg/StartPay" if settings.ZARINPAL_SANDBOX else "https://www.zarinpal.com/pg/StartPay"


class ZarinpalError(RuntimeError):
    pass


async def request_payment(amount_toman: int, description: str, order_id: int) -> tuple[str, str]:
    """
    یک تراکنش پرداخت می‌سازد و (authority, پرداخت‌لینک) را برمی‌گرداند.
    """
    callback_url = f"{settings.ZARINPAL_CALLBACK_BASE_URL}/zarinpal/callback?order_id={order_id}"
    payload = {
        "merchant_id": settings.ZARINPAL_MERCHANT_ID,
        "amount": amount_toman * 10,  # زرین‌پال مبلغ را به ریال می‌خواهد
        "description": description,
        "callback_url": callback_url,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{_BASE}/payment/request.json", json=payload)
    data = resp.json()
    result = data.get("data", {})
    if result.get("code") != 100:
        errors = data.get("errors", {})
        raise ZarinpalError(f"خطا در ایجاد تراکنش زرین‌پال: {errors}")

    authority = result["authority"]
    pay_link = f"{_STARTPAY_BASE}/{authority}"
    return authority, pay_link


async def verify_payment(amount_toman: int, authority: str) -> str:
    """
    پرداخت را وریفای می‌کند و در صورت موفقیت ref_id را برمی‌گرداند، در غیر این‌صورت خطا می‌دهد.
    """
    payload = {
        "merchant_id": settings.ZARINPAL_MERCHANT_ID,
        "amount": amount_toman * 10,
        "authority": authority,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{_BASE}/payment/verify.json", json=payload)
    data = resp.json()
    result = data.get("data", {})
    if result.get("code") not in (100, 101):
        errors = data.get("errors", {})
        raise ZarinpalError(f"وریفای پرداخت ناموفق بود: {errors}")
    return str(result.get("ref_id"))
