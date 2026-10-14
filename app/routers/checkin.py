"""Door check-in: QR validation, duplicate-entry prevention and attendance records."""
import hmac
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, APIRouter
from sqlalchemy import func, select, update

from app.core.deps import CurrentUser, DB, require_roles
from app.core.errors import not_found
from app.models import Booking, BookingItem, CheckIn, Event, EventStaff, User
from app.schemas import ScanIn, ScanOut
from app.services.platform import audit
from app.services.seats import utcnow

router = APIRouter(prefix="/checkin", tags=["Check-in Staff"])

Staff = Annotated[User, Depends(require_roles("checkin", "admin"))]
WINDOW_BEFORE = timedelta(hours=12)  # events listed from 12h before start ...
WINDOW_AFTER = timedelta(hours=18)   # ... until 18h after (covers long festivals / late finishes)


def staff_event(db, user: User, event_id: int) -> Event:
    """The event, only if this staff member is assigned to it (admins may open any)."""
    e = db.get(Event, event_id)
    if not e:
        raise not_found("Event")
    if user.role != "admin" and not db.scalar(
            select(EventStaff.id).where(EventStaff.event_id == event_id, EventStaff.user_id == user.id)):
        raise not_found("Event")  # 404, not 403: do not reveal events the user is not assigned to
    return e


def event_counts(db, event_id: int) -> dict:
    """Tickets sold vs admitted, from confirmed bookings only."""
    qty = (select(BookingItem.booking_id, func.sum(BookingItem.quantity).label("q")).group_by(BookingItem.booking_id).subquery())
    sold, admitted, bookings, arrived = db.execute(
        select(func.coalesce(func.sum(qty.c.q), 0),
               func.coalesce(func.sum(qty.c.q).filter(Booking.checked_in_at.is_not(None)), 0),
               func.count(Booking.id), func.count(Booking.id).filter(Booking.checked_in_at.is_not(None)))
        .select_from(Booking).join(qty, qty.c.booking_id == Booking.id)
        .where(Booking.event_id == event_id, Booking.status == "confirmed")).one()
    return {"tickets_sold": int(sold), "tickets_admitted": int(admitted),
            "bookings": int(bookings), "bookings_arrived": int(arrived)}


@router.get("/events", summary="Events I am assigned to scan for")
def my_events(user: Staff, db: DB):
    now = utcnow()
    q = select(Event).where(Event.status == "approved", Event.starts_at >= now - WINDOW_AFTER,
                            Event.starts_at <= now + timedelta(days=30)).order_by(Event.starts_at)
    if user.role != "admin":
        q = q.where(Event.id.in_(select(EventStaff.event_id).where(EventStaff.user_id == user.id)))
    out = []
    for e in db.scalars(q).unique().all():
        out.append({"id": e.id, "title": e.title, "venue_name": e.venue_name, "starts_at": e.starts_at,
                    "gates_open": e.starts_at - WINDOW_BEFORE <= now, **event_counts(db, e.id)})
    return out


@router.get("/events/{event_id}/stats", summary="Live attendance for an event")
def stats(event_id: int, user: Staff, db: DB):
    e = staff_event(db, user, event_id)
    recent = db.scalars(select(CheckIn).where(CheckIn.event_id == e.id).order_by(CheckIn.id.desc()).limit(15)).unique().all()
    codes = {b.id: b for b in db.scalars(select(Booking).where(Booking.id.in_([r.booking_id for r in recent if r.booking_id])))} if recent else {}
    return {**event_counts(db, e.id), "event": {"id": e.id, "title": e.title, "starts_at": e.starts_at},
            "recent": [{"id": r.id, "result": r.result, "method": r.method, "tickets": r.tickets, "at": r.created_at,
                        "booking_code": codes[r.booking_id].code if r.booking_id in codes else None,
                        "holder_name": codes[r.booking_id].user.name if r.booking_id in codes else None,
                        "staff": r.staff.name if r.staff else None} for r in recent]}


def _log(db, e: Event, user: User, result: str, method: str, b: Booking | None = None, tickets: int = 0) -> None:
    db.add(CheckIn(event_id=e.id, booking_id=b.id if b else None, staff_id=user.id, result=result, method=method,
                   tickets=tickets))


@router.post("/scan", response_model=ScanOut, summary="Validate a ticket QR (or booking code) and admit the party")
def scan(body: ScanIn, user: Staff, db: DB):
    e = staff_event(db, user, body.event_id)
    method = "scan" if body.qr else "manual"

    def reject(result: str, message: str, b: Booking | None = None) -> ScanOut:
        _log(db, e, user, result, method, b)
        db.commit()
        return ScanOut(result=result, message=message, booking_code=b.code if b else None)

    code, token = None, None
    if body.qr:
        parts = body.qr.strip().split("|")
        if len(parts) != 3 or parts[0] != "BMS":
            return reject("invalid", "This is not a BookMyShow ticket QR code.")
        code, token = parts[1], parts[2]
    else:
        code = body.booking_code.strip().upper()

    b = db.scalar(select(Booking).where(Booking.code == code).with_for_update())
    # Constant-time token check; a wrong token never reveals whether the booking exists.
    if not b or (token is not None and not (b.qr_token and hmac.compare_digest(b.qr_token, token))):
        return reject("invalid", "Ticket not recognised. Do not admit.")
    if b.kind != "event" or b.event_id != e.id:
        return reject("wrong_event", f"This ticket is for a different event ({b.event.title if b.event else 'movie show'}).", b)
    if b.status != "confirmed":
        return reject("not_confirmed", f"Booking is {b.status}. Do not admit.", b)

    qty = int(db.scalar(select(func.coalesce(func.sum(BookingItem.quantity), 0)).where(BookingItem.booking_id == b.id)))
    labels = [f"{i.quantity} × {i.label}" for i in b.items]
    # Atomic duplicate guard: only one scan can flip checked_in_at from NULL, however many devices race.
    won = db.execute(update(Booking).where(Booking.id == b.id, Booking.checked_in_at.is_(None))
                     .values(checked_in_at=utcnow(), checked_in_by_id=user.id)).rowcount
    if not won:
        db.refresh(b)
        _log(db, e, user, "duplicate", method, b)
        db.commit()
        return ScanOut(result="duplicate", message="ALREADY SCANNED. This ticket was used earlier. Do not admit again.",
                       booking_code=b.code, holder_name=b.user.name, tickets=qty, items=labels,
                       checked_in_at=b.checked_in_at)
    db.refresh(b)
    _log(db, e, user, "admitted", method, b, qty)
    audit(db, user, "checkin.admit", "booking", b.id, {"event_id": e.id, "tickets": qty, "method": method})
    db.commit()
    return ScanOut(result="admitted", message=f"Admit {qty} guest{'s' if qty != 1 else ''}.", booking_code=b.code,
                   holder_name=b.user.name, tickets=qty, items=labels, checked_in_at=b.checked_in_at)
