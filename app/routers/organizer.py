import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select

from app.core.deps import CurrentUser, DB, OrganizerUser, PageParams, paginate
from app.core.errors import AppError, forbidden, not_found
from app.models import (
    Booking, BookingItem, Event, EventCategory, EventStaff, OrganizerProfile, TicketType, User, Venue,
)
from app.schemas import (
    BookingOut, EventIn, EventOut, Msg, OrganizerOut, OrganizerRegisterIn, Paged, StaffAssignIn, StaffOut, VenueIn,
    VenueOut, partial,
)
from app.services.platform import audit
from app.services.booking import commit
from app.services.seats import utcnow
from app.routers.bookings import booking_out

router = APIRouter(tags=["Organizer Portal (ListYourShow)"])


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:200] or "item"


def unique_slug(db, model, text: str) -> str:
    base = slugify(text)
    slug = base
    while db.scalar(select(model.id).where(model.slug == slug)):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


# ------------------------------------------------------------------ registration (any signed-in user)
@router.post("/organizer/register", response_model=OrganizerOut, status_code=201,
             summary="ListYourShow: apply to become an organizer (admin approval required)")
def register(body: OrganizerRegisterIn, user: CurrentUser, db: DB):
    if db.scalar(select(OrganizerProfile.id).where(OrganizerProfile.user_id == user.id)):
        raise AppError(409, "already_registered", "You have already applied as an organizer")
    p = OrganizerProfile(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    return p


@router.get("/organizer/profile", response_model=OrganizerOut | None)
def profile(user: CurrentUser, db: DB):
    return db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == user.id))


def _own_venue(db, user, venue_id) -> Venue:
    v = db.get(Venue, venue_id)
    if not v or (user.role != "admin" and v.organizer_id != user.id):
        raise not_found("Venue")
    return v


def _own_event(db, user, event_id) -> Event:
    e = db.get(Event, event_id)
    if not e or (user.role != "admin" and e.organizer_id != user.id):
        raise not_found("Event")
    return e


# ------------------------------------------------------------------ venues
@router.get("/organizer/venues", response_model=list[VenueOut])
def my_venues(user: OrganizerUser, db: DB):
    return db.scalars(select(Venue).where(Venue.organizer_id == user.id).order_by(Venue.name)).unique().all()


@router.post("/organizer/venues", response_model=VenueOut, status_code=201, summary="Set up a venue")
def create_venue(body: VenueIn, user: OrganizerUser, db: DB):
    v = Venue(**body.model_dump(), organizer_id=user.id)
    v.type = "venue"
    db.add(v)
    db.commit()
    return v


@router.patch("/organizer/venues/{venue_id}", response_model=VenueOut)
def update_venue(venue_id: int, body: partial(VenueIn), user: OrganizerUser, db: DB):  # type: ignore[valid-type]
    v = _own_venue(db, user, venue_id)
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    return v


@router.delete("/organizer/venues/{venue_id}", response_model=Msg)
def delete_venue(venue_id: int, user: OrganizerUser, db: DB):
    v = _own_venue(db, user, venue_id)
    if db.scalar(select(func.count()).select_from(Event).where(Event.venue_id == v.id)):
        raise AppError(409, "venue_in_use", "This venue has events; deactivate it instead")
    db.delete(v)
    db.commit()
    return Msg(message="Venue deleted")


# ------------------------------------------------------------------ events & ticket inventory
def _apply_event(db, e: Event, body: EventIn, user) -> None:
    cat = db.get(EventCategory, body.category_id)
    if not cat or cat.section != body.section:
        raise AppError(400, "invalid_category", "Category does not belong to the chosen section")
    if body.ends_at and body.ends_at <= body.starts_at:
        raise AppError(400, "invalid_dates", "End time must be after the start time")
    if body.venue_id:
        v = db.get(Venue, body.venue_id)
        if not v or (user.role != "admin" and v.organizer_id != user.id):
            raise not_found("Venue")
        e.venue_name = body.venue_name or v.name
        e.address = body.address or v.address
        e.lat, e.lng = body.lat or v.lat, body.lng or v.lng
    else:
        e.venue_name, e.address, e.lat, e.lng = body.venue_name, body.address, body.lat, body.lng
    for k in ("title", "description", "section", "category_id", "language_id", "city_id", "venue_id", "starts_at",
              "ends_at", "image_url", "color_a", "color_b", "age_limit", "performers"):
        setattr(e, k, getattr(body, k))


def _sync_tickets(db, e: Event, incoming) -> None:
    existing = {t.id: t for t in e.ticket_types}
    keep = set()
    for t in incoming:
        if t.id and t.id in existing:
            tt = existing[t.id]
            if t.total < tt.sold + tt.held:
                raise AppError(400, "inventory_below_sold", f"'{tt.name}': total cannot be below tickets already sold/held")
            tt.name, tt.description, tt.price_paise = t.name, t.description, t.price_paise
            tt.total, tt.max_per_booking = t.total, t.max_per_booking
            keep.add(tt.id)
        else:
            e.ticket_types.append(TicketType(name=t.name, description=t.description, price_paise=t.price_paise,
                                             total=t.total, max_per_booking=t.max_per_booking))
    for tid, tt in existing.items():
        if tid not in keep and incoming and any(x.id for x in incoming):
            if tt.sold or tt.held:
                raise AppError(400, "ticket_in_use", f"'{tt.name}' has sales and cannot be removed")
            e.ticket_types.remove(tt)


@router.get("/organizer/events", response_model=Paged[EventOut])
def my_events(user: OrganizerUser, db: DB, page: PageParams):
    q = select(Event).order_by(Event.starts_at.desc())
    if user.role != "admin":
        q = q.where(Event.organizer_id == user.id)
    return paginate(db, q, page)


@router.post("/organizer/events", response_model=EventOut, status_code=201,
             summary="Create an event (goes to admin review; admins publish instantly)")
def create_event(body: EventIn, user: OrganizerUser, db: DB):
    if user.role == "organizer":
        prof = db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == user.id))
        if not prof or prof.status != "approved":
            raise forbidden("Your organizer account is not approved yet")
    e = Event(organizer_id=user.id, slug=unique_slug(db, Event, body.title),
              status="approved" if user.role == "admin" else "pending")
    _apply_event(db, e, body, user)
    for t in body.ticket_types:
        e.ticket_types.append(TicketType(name=t.name, description=t.description, price_paise=t.price_paise,
                                         total=t.total, max_per_booking=t.max_per_booking))
    db.add(e)
    db.commit()
    return e


@router.put("/organizer/events/{event_id}", response_model=EventOut, summary="Update event details and ticket inventory")
def update_event(event_id: int, body: EventIn, user: OrganizerUser, db: DB):
    e = _own_event(db, user, event_id)
    _apply_event(db, e, body, user)
    _sync_tickets(db, e, body.ticket_types)
    if user.role != "admin" and e.status in ("approved", "rejected"):
        e.status = "pending"  # material edits are re-reviewed
    db.commit()
    return e


@router.post("/organizer/events/{event_id}/cancel", response_model=Msg, summary="Cancel an event and refund all bookings")
def cancel_event(event_id: int, user: OrganizerUser, db: DB):
    from app.services import booking as svc

    e = _own_event(db, user, event_id)
    e.status = "cancelled"
    confirmed = db.scalars(select(Booking).where(Booking.event_id == e.id, Booking.status == "confirmed")
                           .with_for_update(of=Booking)).all()
    n = 0
    for b in confirmed:
        try:
            svc.cancel_booking(db, b, actor_is_admin=True)
            n += 1
        except AppError:
            continue
    commit(db)
    return Msg(message=f"Event cancelled; {n} bookings refunded")


# ------------------------------------------------------------------ bookings & analytics
@router.get("/organizer/bookings", response_model=Paged[BookingOut], summary="Bookings for my events")
def event_bookings(user: OrganizerUser, db: DB, page: PageParams, event_id: int | None = None):
    q = select(Booking).join(Event, Event.id == Booking.event_id).where(Booking.status.in_(["confirmed", "cancelled"]))
    if user.role != "admin":
        q = q.where(Event.organizer_id == user.id)
    if event_id:
        q = q.where(Booking.event_id == event_id)
    res = paginate(db, q.order_by(Booking.created_at.desc()), page)
    res["items"] = [booking_out(b) for b in res["items"]]
    return res


@router.get("/organizer/analytics", summary="Sales analytics for my events")
def analytics(user: OrganizerUser, db: DB, days: int = Query(30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    base = select(Booking).join(Event, Event.id == Booking.event_id)
    scope = [] if user.role == "admin" else [Event.organizer_id == user.id]
    confirmed = Booking.status == "confirmed"

    tot = db.execute(
        select(func.count(Booking.id), func.coalesce(func.sum(Booking.subtotal_paise - Booking.discount_paise), 0))
        .join(Event, Event.id == Booking.event_id).where(confirmed, Booking.confirmed_at >= since, *scope)
    ).one()
    tickets = db.scalar(
        select(func.coalesce(func.sum(BookingItem.quantity), 0)).join(Booking, Booking.id == BookingItem.booking_id)
        .join(Event, Event.id == Booking.event_id).where(confirmed, Booking.confirmed_at >= since, *scope)
    )
    day = func.date_trunc("day", Booking.confirmed_at)
    daily = db.execute(
        select(day.label("d"), func.count(Booking.id), func.sum(Booking.subtotal_paise - Booking.discount_paise))
        .join(Event, Event.id == Booking.event_id).where(confirmed, Booking.confirmed_at >= since, *scope)
        .group_by(day).order_by(day)
    ).all()
    per_event = db.execute(
        select(Event.id, Event.title, func.coalesce(func.sum(TicketType.sold), 0), func.coalesce(func.sum(TicketType.total), 0),
               func.coalesce(func.sum(TicketType.sold * TicketType.price_paise), 0))
        .join(TicketType, TicketType.event_id == Event.id).where(*scope).group_by(Event.id, Event.title)
        .order_by(func.sum(TicketType.sold * TicketType.price_paise).desc()).limit(10)
    ).all()
    return {
        "days": days, "bookings": tot[0], "revenue_paise": int(tot[1]), "tickets": int(tickets),
        "daily": [{"date": d.date().isoformat(), "bookings": c, "revenue_paise": int(r or 0)} for d, c, r in daily],
        "events": [{"id": i, "title": t, "sold": int(s), "capacity": int(c), "revenue_paise": int(r)}
                   for i, t, s, c, r in per_event],
    }


# ------------------------------------------------------------------ door staff & attendees
@router.get("/organizer/events/{event_id}/staff", response_model=list[StaffOut], summary="Check-in staff assigned to my event")
def event_staff(event_id: int, user: OrganizerUser, db: DB):
    e = _own_event(db, user, event_id)
    return [r.user for r in db.scalars(select(EventStaff).where(EventStaff.event_id == e.id).order_by(EventStaff.id)).unique()]


@router.post("/organizer/events/{event_id}/staff", response_model=list[StaffOut], status_code=201,
             summary="Assign a check-in staff account (created by the platform admin) to my event")
def assign_staff(event_id: int, body: StaffAssignIn, user: OrganizerUser, db: DB):
    e = _own_event(db, user, event_id)
    staff = db.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.role == "checkin", User.is_active))
    if not staff:  # one message for "no such user" and "not a check-in account": do not let organizers probe accounts
        raise AppError(404, "staff_not_found",
                       "No active check-in staff account has that email. Ask the platform admin to create one.")
    if not db.scalar(select(EventStaff.id).where(EventStaff.event_id == e.id, EventStaff.user_id == staff.id)):
        db.add(EventStaff(event_id=e.id, user_id=staff.id, assigned_by_id=user.id))
        audit(db, user, "event.staff_assigned", "event", e.id, {"staff_id": staff.id})
        db.commit()
    return event_staff(event_id, user, db)


@router.delete("/organizer/events/{event_id}/staff/{staff_id}", response_model=list[StaffOut])
def unassign_staff(event_id: int, staff_id: int, user: OrganizerUser, db: DB):
    e = _own_event(db, user, event_id)
    row = db.scalar(select(EventStaff).where(EventStaff.event_id == e.id, EventStaff.user_id == staff_id))
    if row:
        db.delete(row)
        audit(db, user, "event.staff_removed", "event", e.id, {"staff_id": staff_id})
        db.commit()
    return event_staff(event_id, user, db)


@router.get("/organizer/events/{event_id}/attendees", summary="Attendee list with check-in status")
def attendees(event_id: int, user: OrganizerUser, db: DB, page: PageParams, q: str | None = Query(None, max_length=80),
              arrived: bool | None = None):
    from app.routers.checkin import event_counts

    e = _own_event(db, user, event_id)
    stmt = (select(Booking).join(User, User.id == Booking.user_id)
            .where(Booking.event_id == e.id, Booking.status == "confirmed").order_by(Booking.id.desc()))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Booking.code.ilike(like) | User.name.ilike(like) | User.email.ilike(like))
    if arrived is not None:
        stmt = stmt.where(Booking.checked_in_at.is_not(None) if arrived else Booking.checked_in_at.is_(None))
    res = paginate(db, stmt, page)
    res["items"] = [{"id": b.id, "code": b.code, "name": b.user.name, "email": b.user.email,
                     "tickets": sum(i.quantity for i in b.items), "items": [f"{i.quantity} × {i.label}" for i in b.items],
                     "confirmed_at": b.confirmed_at, "checked_in_at": b.checked_in_at} for b in res["items"]]
    res["summary"] = event_counts(db, e.id)
    return res
