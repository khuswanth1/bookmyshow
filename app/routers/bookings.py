import logging
from datetime import timedelta
from io import BytesIO
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DB, PageParams, paginate
from app.core.errors import AppError, not_found
from app.models import Booking, Event, Payment, Show
from app.schemas import (
    BookingCreate, BookingOut, CheckoutOut, Msg, Paged, PaymentOut, RazorpayCheckout, VerifyOut, VerifyPaymentIn,
)
from app.services import booking as svc
from app.services import razorpay
from app.services.notify import send_email
from app.services.platform import audit
from app.services.seats import utcnow

log = logging.getLogger("payments")
router = APIRouter(tags=["Bookings & Payments"])


def booking_out(b: Booking) -> BookingOut:
    out = BookingOut.model_validate(b)
    if b.kind == "movie" and b.show:
        s = b.show
        v = s.screen.venue
        out.title, out.subtitle = s.movie.title, f"{s.language.name} · {s.format} · {s.screen.name}"
        out.starts_at, out.venue = s.starts_at, f"{v.name}, {v.city.name}"
        out.poster = {"a": s.movie.color_a, "b": s.movie.color_b, "url": s.movie.poster_url}
    elif b.event:
        e = b.event
        out.title, out.subtitle = e.title, e.category.name
        out.starts_at, out.venue = e.starts_at, f"{e.venue_name}, {e.city.name}"
        out.poster = {"a": e.color_a, "b": e.color_b, "url": e.image_url}
    if b.status == "confirmed" and out.starts_at:
        out.can_cancel = out.starts_at - timedelta(hours=settings.cancellation_cutoff_hours) > utcnow()
        start_fmt = out.starts_at.strftime("%Y%m%dT%H%M%SZ")
        end_time = out.starts_at + timedelta(hours=2, minutes=30)
        end_fmt = end_time.strftime("%Y%m%dT%H%M%SZ")
        items_str = ", ".join(i.label for i in b.items) if b.items else ""
        details = f"Booking Code: {b.code}\nSeats/Tickets: {items_str}\n{out.subtitle}\nVenue: {out.venue}"
        params = {
            "action": "TEMPLATE",
            "text": f"{out.title} - BookMyShow",
            "dates": f"{start_fmt}/{end_fmt}",
            "details": details,
            "location": out.venue,
        }
        out.calendar_url = f"https://calendar.google.com/calendar/render?{urlencode(params)}"
    return out


def _checkout(b: Booking, pay: Payment | None) -> CheckoutOut:
    rz = None
    if pay and b.status == "pending":
        rz = RazorpayCheckout(key_id=settings.razorpay_key_id, order_id=pay.order_id, amount=pay.amount_paise)
    return CheckoutOut(booking=booking_out(b), razorpay=rz)


@router.post("/bookings", response_model=CheckoutOut, status_code=201,
             summary="Create a booking and its Razorpay order (reserves seats / tickets)")
def create_booking(body: BookingCreate, user: CurrentUser, db: DB):
    b, pay = svc.create_booking(
        db, user, kind=body.kind, idempotency_key=body.idempotency_key, show_id=body.show_id, seat_ids=body.seat_ids,
        event_id=body.event_id, tickets=[t.model_dump() for t in body.tickets] if body.tickets else None,
        coupon_code=body.coupon_code, gift_card_code=body.gift_card_code, initiative_id=body.initiative_id,
    )
    return _checkout(b, pay)


@router.get("/bookings", response_model=Paged[BookingOut], summary="My bookings")
def my_bookings(user: CurrentUser, db: DB, page: PageParams,
                scope: Literal["all", "upcoming", "past"] = "all"):
    start = func.coalesce(Show.starts_at, Event.starts_at)
    q = (select(Booking).outerjoin(Show, Show.id == Booking.show_id).outerjoin(Event, Event.id == Booking.event_id)
         .where(Booking.user_id == user.id, Booking.status.in_(["confirmed", "cancelled"])))
    if scope == "upcoming":
        q = q.where(start > utcnow())
    elif scope == "past":
        q = q.where(start <= utcnow())
    res = paginate(db, q.order_by(Booking.created_at.desc()), page)
    res["items"] = [booking_out(b) for b in res["items"]]
    return res


@router.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, user: CurrentUser, db: DB):
    b = db.get(Booking, booking_id)
    if not b or (b.user_id != user.id and user.role != "admin"):
        raise not_found("Booking")
    return booking_out(b)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut,
             summary="Cancel a confirmed booking and refund the ticket value")
def cancel(booking_id: int, user: CurrentUser, db: DB):
    b = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update(of=Booking))
    if not b or (b.user_id != user.id and user.role != "admin"):
        raise not_found("Booking")
    svc.cancel_booking(db, b, actor_is_admin=user.role == "admin")
    audit(db, user, "booking.cancel", "booking", b.id, {"code": b.code, "refund_paise": b.refund_paise})
    svc.commit(db)
    return booking_out(b)


@router.post("/bookings/{booking_id}/abandon", response_model=Msg,
             summary="Release a pending (unpaid) booking's seats / tickets / coupon / gift-card hold")
def abandon(booking_id: int, user: CurrentUser, db: DB):
    b = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update(of=Booking))
    if not b or b.user_id != user.id:
        raise not_found("Booking")
    if b.status == "pending":
        svc.release_booking(db, b, "expired")
        pay = db.scalar(select(Payment).where(Payment.booking_id == b.id, Payment.status == "created"))
        if pay:
            pay.status = "expired"
        svc.commit(db)
    return Msg(message="Released")


@router.post("/bookings/{booking_id}/resend", response_model=Msg, summary="Resend the booking confirmation email")
def resend(booking_id: int, user: CurrentUser, db: DB, bg: BackgroundTasks):
    b = db.get(Booking, booking_id)
    if not b or b.user_id != user.id:
        raise not_found("Booking")
    if b.status != "confirmed":
        raise AppError(409, "not_confirmed", "Only confirmed bookings have tickets")
    o = booking_out(b)
    body = (f"Hi {user.name},\n\nYour booking {b.code} is confirmed.\n{o.title}\n{o.subtitle}\n{o.venue}\n"
            f"{o.starts_at:%a, %d %b %Y %I:%M %p UTC}\nSeats/tickets: {', '.join(i.label for i in b.items)}\n"
            f"Amount paid: ₹{b.total_paise / 100:.2f}\n\nShow this code at the venue: {b.code}\n"
            f"QR: {settings.frontend_url}/bookings/{b.id}\n")
    bg.add_task(send_email, user.email, f"Your tickets: {o.title} ({b.code})", body)
    return Msg(message="Confirmation sent" if settings.smtp_host else "Confirmation queued (email delivery is not configured on this server)")


@router.get("/bookings/code/{code}/qr.png", response_class=Response, summary="QR image for a confirmed booking")
def qr_png(code: str, t: str, db: DB):
    import qrcode

    b = db.scalar(select(Booking).where(Booking.code == code))
    if not b or b.status != "confirmed" or not b.qr_token or t != b.qr_token:
        raise not_found("Ticket")
    img = qrcode.make(f"BMS|{b.code}|{b.qr_token}", box_size=8, border=2)
    buf = BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/bookings/{booking_id}/calendar.ics", response_class=Response, summary="Download .ics calendar event for a booking")
def download_calendar_ics(booking_id: int, user: CurrentUser, db: DB):
    b = db.get(Booking, booking_id)
    if not b or (b.user_id != user.id and user.role != "admin"):
        raise not_found("Booking")
    if b.status != "confirmed":
        raise AppError(409, "not_confirmed", "Only confirmed bookings have calendar events")
    o = booking_out(b)
    if not o.starts_at:
        raise AppError(400, "no_start_time", "No start time found for this booking")

    start_fmt = o.starts_at.strftime("%Y%m%dT%H%M%SZ")
    end_fmt = (o.starts_at + timedelta(hours=2, minutes=30)).strftime("%Y%m%dT%H%M%SZ")
    items_str = ", ".join(i.label for i in b.items) if b.items else ""
    desc = f"Booking Code: {b.code}\\nSeats: {items_str}\\nVenue: {o.venue}"

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//BookMyShow//Ticketing//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{b.code}@bookmyshow\r\n"
        f"DTSTAMP:{start_fmt}\r\n"
        f"DTSTART:{start_fmt}\r\n"
        f"DTEND:{end_fmt}\r\n"
        f"SUMMARY:{o.title} - BookMyShow\r\n"
        f"DESCRIPTION:{desc}\r\n"
        f"LOCATION:{o.venue}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="booking-{b.code}.ics"'},
    )


# ------------------------------------------------------------------ payments
@router.post("/payments/verify", response_model=VerifyOut,
             summary="Verify the Razorpay checkout signature and confirm the booking / activate the gift card")
def verify_payment(body: VerifyPaymentIn, user: CurrentUser, db: DB):
    if not razorpay.verify_checkout_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise AppError(400, "invalid_signature", "Payment signature verification failed")
    pay, b = svc.finalize_paid_order(db, body.razorpay_order_id, body.razorpay_payment_id,
                                     signature=body.razorpay_signature, user_id=user.id)
    code = None
    if pay.purpose == "gift_card":
        from app.models import GiftCard
        code = db.get(GiftCard, pay.gift_card_id).code
    svc.commit(db)
    return VerifyOut(status="paid", booking=booking_out(b) if b else None, gift_card_code=code)


@router.post("/payments/webhook", include_in_schema=True, summary="Razorpay webhook (signature protected)")
async def webhook(request: Request, db: DB, x_razorpay_signature: str = Header(default="")):
    raw = await request.body()
    if not settings.razorpay_webhook_secret:
        raise AppError(503, "webhook_disabled", "Webhook secret is not configured")
    if not razorpay.verify_webhook_signature(raw, x_razorpay_signature):
        raise AppError(400, "invalid_signature", "Bad webhook signature")
    import json

    event = json.loads(raw)
    name = event.get("event", "")
    ent = (event.get("payload", {}).get("payment", {}) or {}).get("entity", {})
    if name in ("payment.captured", "order.paid") and ent.get("order_id"):
        try:
            svc.finalize_paid_order(db, ent["order_id"], ent["id"], method=ent.get("method"))
            svc.commit(db)
        except AppError as e:  # unknown order / already refunded: acknowledge so Razorpay stops retrying
            db.rollback()
            log.warning("webhook %s ignored: %s", name, e.code)
    elif name == "payment.failed" and ent.get("order_id"):
        pay = db.scalar(select(Payment).where(Payment.order_id == ent["order_id"]).with_for_update())
        if pay and pay.status == "created":
            pay.status = "failed"
            db.commit()
    return {"status": "ok"}


@router.get("/payments", response_model=Paged[PaymentOut], summary="My payment history")
def my_payments(user: CurrentUser, db: DB, page: PageParams):
    q = select(Payment).where(Payment.user_id == user.id, Payment.status != "created").order_by(Payment.created_at.desc())
    res = paginate(db, q, page)
    res["items"] = [
        PaymentOut.model_validate(p).model_copy(update={"booking_code": p.booking.code if p.booking else None})
        for p in res["items"]
    ]
    return res
