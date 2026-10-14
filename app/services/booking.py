"""Booking engine: reserve -> pay -> confirm, plus expiry, cancellation and refunds.

Invariants (all enforced inside one DB transaction with row locks):
  * A show seat is `booked` for at most one booking (ShowSeat.booking_id is the single source of truth).
  * Seats/inventory/coupon/gift-card amounts are *reserved* when the booking is created and *released*
    exactly once when it expires, fails or is cancelled (`release_booking`).
  * `confirm_booking` is idempotent; payment verification and the webhook can race safely.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, conflict, not_found
from app.models import (
    Booking, BookingItem, Coupon, CouponRedemption, Event, GiftCard, Initiative, Payment, Show, ShowSeat,
    TicketType, User, VendorProfile,
)
from app.services import razorpay
from app.services import gcal
from app.services.notify import notify
from app.services.platform import commission_for, show_is_public
from app.services.pricing import fees, load_valid_coupon
from app.services.realtime import publish_seats, publish_user

log = logging.getLogger("booking")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def commit(db: Session) -> None:
    """Commit, then run realtime callbacks. Callbacks never run for rolled-back work."""
    callbacks = db.info.pop("after_commit", [])
    db.commit()
    for cb in callbacks:
        try:
            cb()
        except Exception:
            log.exception("after_commit callback failed")


def _defer(db: Session, fn) -> None:
    db.info.setdefault("after_commit", []).append(fn)


def _seat_event(db: Session, show_id: int, seats: list[dict]) -> None:
    if seats:
        _defer(db, lambda: publish_seats(show_id, seats))


def new_code() -> str:
    return "BMS" + "".join(secrets.choice(ALPHABET) for _ in range(8))


# --------------------------------------------------------------------------- release
def release_booking(db: Session, b: Booking, new_status: str, restore_gift: int | None = None,
                    keep_seat_ids: frozenset[int] = frozenset()) -> None:
    """Undo every reservation a booking holds and move it to `new_status`. Idempotent per status."""
    if b.status not in ("pending", "confirmed"):
        return
    was_confirmed = b.status == "confirmed"
    if b.kind == "movie":
        seats = db.scalars(
            select(ShowSeat).where(ShowSeat.booking_id == b.id).order_by(ShowSeat.id).with_for_update()
        ).all()
        changes = []
        for s in seats:
            s.booking_id = None
            if s.id in keep_seat_ids:
                continue  # stays locked by the same user for the replacement booking
            s.status, s.locked_by, s.locked_until = "available", None, None
            changes.append({"id": s.id, "status": "available"})
        if b.show_id:
            _seat_event(db, b.show_id, changes)
    else:
        for it in sorted(b.items, key=lambda i: i.ticket_type_id or 0):
            if not it.ticket_type_id:
                continue
            tt = db.scalar(select(TicketType).where(TicketType.id == it.ticket_type_id).with_for_update())
            if tt:
                if was_confirmed:
                    tt.sold = max(0, tt.sold - it.quantity)
                else:
                    tt.held = max(0, tt.held - it.quantity)
    gift = b.gift_card_paise if restore_gift is None else restore_gift
    if b.gift_card_id and gift > 0:
        g = db.scalar(select(GiftCard).where(GiftCard.id == b.gift_card_id).with_for_update())
        if g:
            g.balance_paise += gift
            if g.status == "exhausted":
                g.status = "active"
    red = db.scalar(select(CouponRedemption).where(CouponRedemption.booking_id == b.id))
    if red:
        c = db.scalar(select(Coupon).where(Coupon.id == red.coupon_id).with_for_update())
        if c:
            c.used_count = max(0, c.used_count - 1)
        db.delete(red)
    b.status = new_status
    if new_status == "cancelled":
        b.cancelled_at = utcnow()


def expire_pending_bookings(db: Session) -> int:
    rows = db.scalars(
        select(Booking)
        .where(Booking.status == "pending", Booking.expires_at < utcnow())
        .with_for_update(skip_locked=True, of=Booking)
    ).all()
    for b in rows:
        release_booking(db, b, "expired")
        pay = db.scalar(select(Payment).where(Payment.booking_id == b.id, Payment.status == "created"))
        if pay:
            pay.status = "expired"
    return len(rows)


# --------------------------------------------------------------------------- create
def _collect_movie_items(db: Session, user: User, show_id: int, seat_ids: list[int], old_pending: list[Booking]):
    show = db.get(Show, show_id)
    if not show or not show_is_public(db, show):
        raise not_found("Show")
    if show.starts_at <= utcnow():
        raise AppError(409, "show_closed", "Booking is closed for this show")
    if not seat_ids or len(set(seat_ids)) != len(seat_ids):
        raise AppError(400, "invalid_seats", "Select at least one seat")
    if len(seat_ids) > settings.max_seats_per_booking:
        raise AppError(400, "too_many_seats", f"You can book up to {settings.max_seats_per_booking} seats at once")
    old_ids = set()
    if old_pending:
        old_ids = set(db.scalars(select(ShowSeat.id).where(ShowSeat.booking_id.in_([o.id for o in old_pending]))))
    # lock new + previously-attached seats in one ordered statement (deadlock-free)
    rows = {
        r.id: r
        for r in db.scalars(
            select(ShowSeat).where(ShowSeat.id.in_(set(seat_ids) | old_ids)).order_by(ShowSeat.id).with_for_update()
        )
    }
    now = utcnow()
    bad = []
    for i in seat_ids:
        r = rows.get(i)
        if not r or r.show_id != show.id:
            raise not_found("Seat")
        if not (r.status == "locked" and r.locked_by == user.id and r.locked_until and r.locked_until > now):
            bad.append(i)
    if bad:
        raise conflict("Your seat hold expired or was lost. Please select seats again.", "seat_unavailable",
                       {"seat_ids": bad})
    for o in old_pending:
        release_booking(db, o, "expired", keep_seat_ids=frozenset(seat_ids))
    subtotal = sum(rows[i].price_paise for i in seat_ids)
    return show, rows, subtotal


def create_booking(
    db: Session, user: User, *, kind: str, idempotency_key: str, show_id: int | None = None,
    seat_ids: list[int] | None = None, event_id: int | None = None, tickets: list[dict] | None = None,
    coupon_code: str | None = None, gift_card_code: str | None = None, initiative_id: int | None = None,
) -> tuple[Booking, Payment | None]:
    existing = db.scalar(select(Booking).where(Booking.user_id == user.id, Booking.idempotency_key == idempotency_key))
    if existing:
        pay = db.scalar(select(Payment).where(Payment.booking_id == existing.id).order_by(Payment.id.desc()))
        return existing, pay

    now = utcnow()
    window = now + timedelta(minutes=settings.payment_window_minutes)
    items: list[BookingItem] = []
    rows: dict[int, ShowSeat] = {}
    tts: dict[int, TicketType] = {}

    if kind == "movie":
        if show_id is None:
            raise AppError(400, "invalid_request", "show_id is required")
        old = list(db.scalars(
            select(Booking).where(Booking.user_id == user.id, Booking.show_id == show_id, Booking.status == "pending")
            .with_for_update()
        ))
        show, rows, subtotal = _collect_movie_items(db, user, show_id, seat_ids or [], old)
        for i in seat_ids:
            r = rows[i]
            items.append(BookingItem(show_seat_id=r.id, label=f"{r.seat.row_label}{r.seat.number} · {r.category}",
                                     quantity=1, unit_price_paise=r.price_paise))
        starts_at = show.starts_at
    else:
        if event_id is None or not tickets:
            raise AppError(400, "invalid_request", "event_id and tickets are required")
        ev = db.get(Event, event_id)
        if not ev or ev.status != "approved":
            raise not_found("Event")
        if ev.starts_at <= now:
            raise AppError(409, "event_closed", "Booking is closed for this event")
        want: dict[int, int] = {}
        for t in tickets:
            want[t["ticket_type_id"]] = want.get(t["ticket_type_id"], 0) + t["quantity"]
        locked = db.scalars(
            select(TicketType).where(TicketType.id.in_(want), TicketType.event_id == ev.id)
            .order_by(TicketType.id).with_for_update()
        ).all()
        if len(locked) != len(want):
            raise not_found("Ticket type")
        subtotal = 0
        for tt in locked:
            q = want[tt.id]
            if q > tt.max_per_booking:
                raise AppError(400, "limit_exceeded", f"Max {tt.max_per_booking} '{tt.name}' tickets per booking")
            if tt.total - tt.sold - tt.held < q:
                raise conflict(f"Only {max(0, tt.total - tt.sold - tt.held)} '{tt.name}' tickets left", "sold_out")
            tt.held += q
            tts[tt.id] = tt
            subtotal += tt.price_paise * q
            items.append(BookingItem(ticket_type_id=tt.id, label=tt.name, quantity=q, unit_price_paise=tt.price_paise))
        starts_at = ev.starts_at

    # --- coupon (row-locked so usage limits are exact)
    coupon, discount = None, 0
    if coupon_code:
        coupon, discount = load_valid_coupon(db, coupon_code, user.id, kind, subtotal, lock=True)

    # --- donation
    donation, init_id = 0, None
    if initiative_id:
        ini = db.get(Initiative, initiative_id)
        if not ini or not ini.is_active:
            raise AppError(400, "invalid_initiative", "This initiative is not available")
        donation, init_id = ini.amount_paise, ini.id

    fee, tax = fees(subtotal - discount)
    total = subtotal - discount + fee + tax + donation

    # --- gift card (balance deducted now, restored on release)
    gift, gift_applied = None, 0
    if gift_card_code:
        gift = db.scalar(select(GiftCard).where(GiftCard.code == gift_card_code.strip().upper()).with_for_update())
        if not gift or gift.status != "active" or (gift.expires_at and gift.expires_at < now):
            raise AppError(400, "invalid_gift_card", "This gift card is not valid")
        gift_applied = min(gift.balance_paise, total)
        if gift_applied <= 0:
            raise AppError(400, "gift_card_empty", "This gift card has no balance left")
        gift.balance_paise -= gift_applied
        if gift.balance_paise == 0:
            gift.status = "exhausted"

    b = Booking(
        code=new_code(), user_id=user.id, kind=kind, show_id=show_id if kind == "movie" else None,
        event_id=event_id if kind == "event" else None, status="pending", subtotal_paise=subtotal, fee_paise=fee,
        tax_paise=tax, discount_paise=discount, donation_paise=donation, gift_card_paise=gift_applied,
        total_paise=total, payable_paise=total - gift_applied, coupon_id=coupon.id if coupon else None,
        gift_card_id=gift.id if gift else None, initiative_id=init_id, idempotency_key=idempotency_key,
        expires_at=window, items=items,
    )
    db.add(b)
    db.flush()
    if kind == "movie":
        changes = []
        for r in rows.values():
            if r.id in seat_ids:
                r.booking_id, r.locked_until = b.id, window
                changes.append({"id": r.id, "status": "locked"})
    if coupon:
        coupon.used_count += 1
        db.add(CouponRedemption(coupon_id=coupon.id, user_id=user.id, booking_id=b.id))
    db.flush()

    if b.payable_paise == 0:  # fully covered by gift card / discount
        confirm_booking(db, b)
        commit(db)
        return b, None

    commit(db)  # reservation is durable before we call the gateway
    try:
        order = razorpay.create_order(b.payable_paise, receipt=b.code, notes={"booking": b.code, "user": str(user.id)})
    except AppError:
        release_booking(db, b, "failed")
        commit(db)
        raise
    pay = Payment(purpose="booking", booking_id=b.id, user_id=user.id, order_id=order["id"],
                  amount_paise=b.payable_paise, status="created", raw={"order": order})
    db.add(pay)
    commit(db)
    return b, pay


# --------------------------------------------------------------------------- confirm
def _reclaim(db: Session, b: Booking) -> bool:
    """A payment arrived after the hold expired. Re-take the same inventory if it is still free."""
    now = utcnow()
    if b.kind == "movie":
        item_ids = [i.show_seat_id for i in b.items if i.show_seat_id]
        if len(item_ids) != len(b.items):
            return False
        rows = db.scalars(select(ShowSeat).where(ShowSeat.id.in_(item_ids)).order_by(ShowSeat.id).with_for_update()).all()
        ok = all(
            r.status == "available"
            or (r.status == "locked" and (r.locked_by == b.user_id or (r.locked_until and r.locked_until <= now)))
            for r in rows
        ) and len(rows) == len(item_ids)
        if not ok:
            return False
        for r in rows:
            r.status, r.locked_by, r.locked_until, r.booking_id = "locked", b.user_id, None, b.id
    else:
        for it in sorted(b.items, key=lambda i: i.ticket_type_id or 0):
            tt = db.scalar(select(TicketType).where(TicketType.id == it.ticket_type_id).with_for_update())
            if not tt or tt.total - tt.sold - tt.held < it.quantity:
                return False
            tt.held += it.quantity
    if b.gift_card_id and b.gift_card_paise:
        g = db.scalar(select(GiftCard).where(GiftCard.id == b.gift_card_id).with_for_update())
        if not g or g.balance_paise < b.gift_card_paise:
            return False
        g.balance_paise -= b.gift_card_paise
    db.flush()  # sessions run with autoflush off
    return True


def confirm_booking(db: Session, b: Booking) -> Booking:
    """Idempotent. Caller must hold the booking row lock (SELECT ... FOR UPDATE)."""
    if b.status == "confirmed":
        return b
    if b.status != "pending":
        if not _reclaim(db, b):
            raise AppError(409, "booking_expired", "This booking expired and the seats are no longer available")
    seats = []
    if b.kind == "movie":
        seats = db.scalars(select(ShowSeat).where(ShowSeat.booking_id == b.id).order_by(ShowSeat.id).with_for_update()).all()
        if len(seats) != len(b.items):
            raise AppError(409, "seat_conflict", "Seat state changed; booking cannot be confirmed")
    b.status, b.confirmed_at, b.expires_at = "confirmed", utcnow(), None
    b.qr_token = secrets.token_urlsafe(24)
    if b.kind == "movie":
        changes = []
        for s in seats:
            s.status, s.locked_by, s.locked_until = "booked", None, None
            changes.append({"id": s.id, "status": "booked"})
        if b.show_id:
            _seat_event(db, b.show_id, changes)
        title = b.show.movie.title if b.show else "your movie"
        _book_commission(db, b)
    else:
        for it in sorted(b.items, key=lambda i: i.ticket_type_id or 0):
            tt = db.scalar(select(TicketType).where(TicketType.id == it.ticket_type_id).with_for_update())
            tt.held = max(0, tt.held - it.quantity)
            tt.sold += it.quantity
        title = b.event.title if b.event else "your event"
    uid, code = b.user_id, b.code
    notify(db, uid, "Booking confirmed 🎟️", f"Your booking {code} for {title} is confirmed.", "booking")
    _defer(db, lambda: publish_user(uid, {"type": "booking", "status": "confirmed", "code": code}))
    bid = b.id
    _defer(db, lambda: gcal.background(gcal.sync_booking, bid))
    return b


def _book_commission(db: Session, b: Booking) -> None:
    """Split the net ticket value between the theater vendor and the platform."""
    venue = b.show.screen.venue if b.show else None
    if not venue or not venue.vendor_id:
        return
    vendor = db.get(VendorProfile, venue.vendor_id)
    net = max(0, b.subtotal_paise - b.discount_paise)
    pct = commission_for(db, vendor)
    b.vendor_id, b.commission_pct = vendor.id, pct
    b.commission_paise = round(net * pct / 100)
    b.vendor_share_paise = net - b.commission_paise
    notify(db, vendor.user_id, "New booking",
           f"{b.code}: {len(b.items)} seat(s) for {b.show.movie.title} ({b.show.starts_at:%d %b %H:%M} UTC).", "vendor")


def refund_whole_payment(db: Session, pay: Payment, reason: str) -> None:
    try:
        r = razorpay.refund_payment(pay.payment_id, pay.amount_paise, {"reason": reason})
        pay.refund_id, pay.refund_paise, pay.status = r.get("id"), pay.amount_paise, "refunded"
    except AppError:
        log.critical("AUTO-REFUND FAILED payment=%s order=%s — needs manual refund", pay.payment_id, pay.order_id)
        pay.status = "paid_needs_refund"


def finalize_paid_order(db: Session, order_id: str, payment_id: str, *, signature: str | None = None,
                        method: str | None = None, user_id: int | None = None) -> tuple[Payment, Booking | None]:
    """Mark an order paid and fulfil it. Safe to call repeatedly / concurrently."""
    pay = db.scalar(select(Payment).where(Payment.order_id == order_id).with_for_update())
    if not pay or (user_id is not None and pay.user_id != user_id):
        raise not_found("Payment")
    if pay.status in ("paid", "refunded", "paid_needs_refund"):
        b = db.get(Booking, pay.booking_id) if pay.booking_id else None
        return pay, b
    pay.payment_id, pay.signature, pay.status = payment_id, signature, "paid"
    pay.method = method or pay.method

    if pay.purpose == "gift_card":
        g = db.scalar(select(GiftCard).where(GiftCard.id == pay.gift_card_id).with_for_update())
        g.status, g.code = "active", g.code or ("GC" + "".join(secrets.choice(ALPHABET) for _ in range(12)))
        g.expires_at = utcnow() + timedelta(days=365)
        notify(db, g.purchaser_id, "Gift card ready 🎁", f"Gift card {g.code} worth ₹{g.initial_paise // 100} is active.", "gift")
        return pay, None

    b = db.scalar(select(Booking).where(Booking.id == pay.booking_id).with_for_update(of=Booking))
    try:
        confirm_booking(db, b)
    except AppError as e:
        if e.code in ("booking_expired", "seat_conflict"):
            # Money was captured but inventory is gone: refund automatically.
            b.status = "failed"
            refund_whole_payment(db, pay, "inventory_unavailable")
            notify(db, b.user_id, "Booking failed — refund initiated",
                   f"Seats for {b.code} were no longer available. Your payment is being refunded.", "booking")
            commit(db)
            raise AppError(409, "booking_failed_refunded",
                           "Seats were no longer available. Your payment has been refunded.") from e
        raise
    return pay, b


# --------------------------------------------------------------------------- cancel
def cancel_booking(db: Session, b: Booking, actor_is_admin: bool = False) -> Booking:
    if b.status != "confirmed":
        raise AppError(409, "not_cancellable", "Only confirmed bookings can be cancelled")
    if b.checked_in_at and not actor_is_admin:
        raise AppError(409, "already_checked_in", "This booking was already used at the venue and can no longer be cancelled")
    start = b.show.starts_at if b.show else (b.event.starts_at if b.event else None)
    cutoff = timedelta(hours=settings.cancellation_cutoff_hours)
    if not actor_is_admin and start and start - cutoff < utcnow():
        raise AppError(409, "cancellation_closed",
                       f"Cancellation closes {settings.cancellation_cutoff_hours} hours before the start time")
    # Convenience fee, GST and donation are non-refundable.
    refundable = max(0, b.subtotal_paise - b.discount_paise)
    to_gateway = min(b.payable_paise, refundable)
    to_gift = min(b.gift_card_paise, refundable - to_gateway)
    pay = db.scalar(select(Payment).where(Payment.booking_id == b.id, Payment.status == "paid").with_for_update())
    if to_gateway > 0:
        if not pay or not pay.payment_id:
            raise AppError(409, "refund_unavailable", "No captured payment found to refund")
        r = razorpay.refund_payment(pay.payment_id, to_gateway, {"booking": b.code})
        pay.refund_id, pay.refund_paise = r.get("id"), to_gateway
        pay.status = "refunded" if to_gateway >= pay.amount_paise else "partially_refunded"
    release_booking(db, b, "cancelled", restore_gift=to_gift)
    if b.calendar_event_id:
        bid = b.id
        _defer(db, lambda: gcal.background(gcal.remove_booking, bid))
    b.refund_paise = to_gateway + to_gift
    notify(db, b.user_id, "Booking cancelled",
           f"{b.code} was cancelled. ₹{b.refund_paise / 100:.2f} will be refunded.", "booking")
    uid, code = b.user_id, b.code
    _defer(db, lambda: publish_user(uid, {"type": "booking", "status": "cancelled", "code": code}))
    return b
