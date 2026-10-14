from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models import Coupon, CouponRedemption


def fees(subtotal: int) -> tuple[int, int]:
    """Convenience fee on the ticket subtotal, and GST charged on that fee (paise)."""
    fee = round(subtotal * settings.convenience_fee_pct / 100)
    tax = round(fee * settings.gst_pct / 100)
    return fee, tax


def coupon_discount(coupon: Coupon, subtotal: int) -> int:
    if coupon.discount_type == "percent":
        d = subtotal * coupon.value // 100
    else:
        d = coupon.value
    if coupon.max_discount_paise:
        d = min(d, coupon.max_discount_paise)
    return max(0, min(d, subtotal))


def load_valid_coupon(
    db: Session, code: str, user_id: int, kind: str, subtotal: int, lock: bool = False
) -> tuple[Coupon, int]:
    q = select(Coupon).where(func.upper(Coupon.code) == code.strip().upper())
    if lock:
        q = q.with_for_update()
    c = db.scalar(q)
    now = datetime.now(timezone.utc)
    if not c or not c.is_active:
        raise AppError(400, "invalid_coupon", "This coupon code is not valid")
    if (c.starts_at and c.starts_at > now) or (c.ends_at and c.ends_at < now):
        raise AppError(400, "coupon_expired", "This coupon is not active right now")
    if c.applies_to not in ("all", kind):
        raise AppError(400, "coupon_not_applicable", f"This coupon is not valid for {kind} bookings")
    if subtotal < c.min_order_paise:
        raise AppError(400, "coupon_min_order", f"Minimum order of ₹{c.min_order_paise // 100} required")
    if c.usage_limit is not None and c.used_count >= c.usage_limit:
        raise AppError(400, "coupon_exhausted", "This coupon has been fully redeemed")
    used = db.scalar(
        select(func.count()).select_from(CouponRedemption).where(
            CouponRedemption.coupon_id == c.id, CouponRedemption.user_id == user_id
        )
    )
    if used >= c.per_user_limit:
        raise AppError(400, "coupon_already_used", "You have already used this coupon")
    return c, coupon_discount(c, subtotal)
