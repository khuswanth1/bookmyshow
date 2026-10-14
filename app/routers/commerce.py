from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import and_, or_, select

from app.core.deps import CurrentUser, DB
from app.core.errors import AppError, not_found
from app.models import Coupon, GiftCard, Payment
from app.schemas import (
    CouponOut, CouponValidateIn, CouponValidateOut, GiftCardBalance, GiftCardCheckout, GiftCardCreate, GiftCardOut,
    RazorpayCheckout,
)
from app.core.config import settings
from app.services import razorpay
from app.services.booking import commit
from app.services.pricing import load_valid_coupon

router = APIRouter(tags=["Offers & Gift Cards"])


@router.get("/offers", response_model=list[CouponOut], summary="Public promotional offers (general, bank, corporate)")
def offers(db: DB, kind: str | None = None):
    now = datetime.now(timezone.utc)
    q = select(Coupon).where(
        Coupon.is_active, Coupon.is_public,
        or_(Coupon.ends_at.is_(None), Coupon.ends_at > now),
        or_(Coupon.usage_limit.is_(None), Coupon.used_count < Coupon.usage_limit),
    ).order_by(Coupon.id.desc())
    if kind:
        q = q.where(Coupon.kind == kind)
    return db.scalars(q).all()


@router.post("/coupons/validate", response_model=CouponValidateOut, summary="Preview a coupon's discount for a subtotal")
def validate_coupon(body: CouponValidateIn, user: CurrentUser, db: DB):
    c, d = load_valid_coupon(db, body.code, user.id, body.kind, body.subtotal_paise)
    return CouponValidateOut(code=c.code, title=c.title, discount_paise=d)


@router.post("/gift-cards", response_model=GiftCardCheckout, status_code=201,
             summary="Buy a gift card (creates a Razorpay order; card activates on payment)")
def buy_gift_card(body: GiftCardCreate, user: CurrentUser, db: DB):
    g = GiftCard(initial_paise=body.amount_paise, balance_paise=body.amount_paise, purchaser_id=user.id,
                 recipient_name=body.recipient_name, recipient_email=str(body.recipient_email).lower(),
                 message=body.message, status="pending")
    db.add(g)
    db.flush()
    order = razorpay.create_order(body.amount_paise, receipt=f"GC{g.id}", notes={"gift_card": str(g.id)})
    db.add(Payment(purpose="gift_card", gift_card_id=g.id, user_id=user.id, order_id=order["id"],
                   amount_paise=body.amount_paise, raw={"order": order}))
    commit(db)
    return GiftCardCheckout(
        gift_card=GiftCardOut.model_validate(g),
        razorpay=RazorpayCheckout(key_id=settings.razorpay_key_id, order_id=order["id"], amount=body.amount_paise),
    )


@router.get("/gift-cards/mine", response_model=list[GiftCardOut], summary="Gift cards I bought or received")
def my_gift_cards(user: CurrentUser, db: DB):
    return db.scalars(
        select(GiftCard).where(
            GiftCard.status != "pending",
            or_(GiftCard.purchaser_id == user.id, GiftCard.recipient_email == user.email.lower()),
        ).order_by(GiftCard.id.desc())
    ).all()


@router.get("/gift-cards/check/{code}", response_model=GiftCardBalance, summary="Check a gift card balance")
def check_gift_card(code: str, user: CurrentUser, db: DB):
    g = db.scalar(select(GiftCard).where(GiftCard.code == code.strip().upper()))
    if not g or g.status == "pending":
        raise not_found("Gift card")
    return GiftCardBalance(code=g.code, balance_paise=g.balance_paise, status=g.status, expires_at=g.expires_at)
