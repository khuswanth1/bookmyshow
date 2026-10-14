"""Thin Razorpay REST client (Orders, Payments, Refunds) + signature verification."""
import logging

import httpx

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hmac_sha256, safe_eq

log = logging.getLogger("razorpay")
BASE = "https://api.razorpay.com/v1"


def _client() -> httpx.Client:
    if not settings.razorpay_enabled:
        raise AppError(503, "payments_unavailable", "Payments are not configured on this server")
    return httpx.Client(base_url=BASE, auth=(settings.razorpay_key_id, settings.razorpay_key_secret), timeout=15)


def _call(method: str, path: str, **kw) -> dict:
    try:
        with _client() as c:
            r = c.request(method, path, **kw)
    except httpx.HTTPError as e:
        log.error("razorpay network error: %s", e)
        raise AppError(502, "payment_gateway_error", "Could not reach the payment gateway, please retry")
    if r.status_code >= 400:
        log.error("razorpay %s %s -> %s %s", method, path, r.status_code, r.text[:300])
        try:
            desc = r.json().get("error", {}).get("description", "")
        except Exception:
            desc = ""
        raise AppError(502, "payment_gateway_error", f"Payment gateway rejected the request. {desc}".strip())
    return r.json()


def create_order(amount_paise: int, receipt: str, notes: dict | None = None) -> dict:
    return _call(
        "POST", "/orders",
        json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes or {}},
    )


def fetch_payment(payment_id: str) -> dict:
    return _call("GET", f"/payments/{payment_id}")


def refund_payment(payment_id: str, amount_paise: int, notes: dict | None = None) -> dict:
    return _call("POST", f"/payments/{payment_id}/refund", json={"amount": amount_paise, "notes": notes or {}})


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not settings.razorpay_key_secret:
        return False
    return safe_eq(hmac_sha256(settings.razorpay_key_secret, f"{order_id}|{payment_id}"), signature or "")


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False
    return safe_eq(hmac_sha256(settings.razorpay_webhook_secret, raw_body), signature or "")
