from datetime import datetime, time, timedelta, timezone
from typing import Callable

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, func, or_, select

from app.core.deps import AdminUser, DB, PageParams, paginate, require_roles
from app.core.errors import AppError, conflict, not_found
from app.core.security import hash_password
from app.models import (
    Booking, City, Coupon, Event, EventCategory, Faq, Genre, GiftCard, Initiative, Language, Movie, NewsletterSubscriber,
    OrganizerProfile, Payment, Screen, Seat, Show, SupportMessage, SupportTicket, User, Venue, Video,
)
from app.routers.bookings import booking_out
from app.routers.organizer import unique_slug
from app.schemas import (
    AdminUserUpdate, BookingOut, CategoryIn, CategoryOut, CityIn, CityOut, CouponIn, CouponOut, EventAdminPatch,
    EventOut, FaqIn, FaqOut, GenreIn, GenreOut, GiftCardOut, InitiativeIn, InitiativeOut, LanguageIn, LanguageOut, Msg,
    MovieIn, MovieOut, OrganizerOut, OrganizerReview, Paged, PaymentOut, ScreenIn, ScreenOut, ShowBulkIn, ShowOut,
    StaffCreateIn, SupportAdminPatch, SupportOut, UserOut, VenueIn, VenueOut, VideoIn, VideoOut, partial,
)
from app.services import booking as bsvc
from app.services import scheduling
from app.services import seats as seat_svc
from app.services.platform import audit
from app.services.notify import notify
from app.services.seats import utcnow

router = APIRouter(prefix="/admin", tags=["Admin Panel"], dependencies=[Depends(require_roles("admin"))])


def _assign(obj, model, data: dict) -> None:
    cols = {c.key for c in model.__table__.columns}
    for k, v in data.items():
        if k in cols:
            setattr(obj, k, v)


def crud(path: str, model, In, Out, *, search: tuple = (), order=None, hook: Callable | None = None,
         filters: dict | None = None, slug_from: str | None = None):
    """Register list/create/get/patch/delete for a simple resource."""
    Patch = partial(In, f"{In.__name__}Update")
    order_cols = order if order is not None else (model.id.desc(),)

    @router.get(f"/{path}", response_model=Paged[Out], name=f"list_{path}", summary=f"List {path}")
    def list_(db: DB, page: PageParams, q: str | None = Query(None, max_length=100)):
        stmt = select(model)
        if q and search:
            stmt = stmt.where(or_(*[cast(getattr(model, s), String).ilike(f"%{q}%") for s in search]))
        return paginate(db, stmt.order_by(*order_cols), page)

    @router.post(f"/{path}", response_model=Out, status_code=201, name=f"create_{path}", summary=f"Create {path[:-1]}")
    def create(body: In, db: DB, admin: AdminUser):  # type: ignore[valid-type]
        data = body.model_dump()
        obj = model()
        _assign(obj, model, data)
        if slug_from and hasattr(model, "slug") and not getattr(obj, "slug", None):
            obj.slug = unique_slug(db, model, data[slug_from])
        db.add(obj)
        if hook:
            hook(db, obj, data)
        db.flush()
        audit(db, admin, f"{path}.create", path, obj.id)
        db.commit()
        return obj

    @router.get(f"/{path}/{{item_id}}", response_model=Out, name=f"get_{path}", summary=f"Get {path[:-1]}")
    def get(item_id: int, db: DB):
        obj = db.get(model, item_id)
        if not obj:
            raise not_found(path[:-1].title())
        return obj

    @router.patch(f"/{path}/{{item_id}}", response_model=Out, name=f"update_{path}", summary=f"Update {path[:-1]}")
    def update(item_id: int, body: Patch, db: DB, admin: AdminUser):  # type: ignore[valid-type]
        obj = db.get(model, item_id)
        if not obj:
            raise not_found(path[:-1].title())
        data = body.model_dump(exclude_unset=True)
        _assign(obj, model, data)
        if hook:
            hook(db, obj, data)
        audit(db, admin, f"{path}.update", path, item_id, {"fields": sorted(data)})
        db.commit()
        return obj

    @router.delete(f"/{path}/{{item_id}}", response_model=Msg, name=f"delete_{path}", summary=f"Delete {path[:-1]}")
    def delete(item_id: int, db: DB, admin: AdminUser):
        obj = db.get(model, item_id)
        if not obj:
            raise not_found(path[:-1].title())
        db.delete(obj)
        audit(db, admin, f"{path}.delete", path, item_id)
        db.commit()  # FK violations surface as a 409 via the IntegrityError handler
        return Msg(message="Deleted")


# ---- simple reference data
crud("cities", City, CityIn, CityOut, search=("name", "state", "country"), order=(City.name,))
crud("genres", Genre, GenreIn, GenreOut, search=("name",), order=(Genre.name,))
crud("languages", Language, LanguageIn, LanguageOut, search=("name", "code"), order=(Language.name,))
crud("categories", EventCategory, CategoryIn, CategoryOut, search=("name", "section"), order=(EventCategory.section, EventCategory.name))
crud("coupons", Coupon, CouponIn, CouponOut, search=("code", "title", "kind"))
crud("faqs", Faq, FaqIn, FaqOut, search=("question", "category"), order=(Faq.category, Faq.sort_order))
crud("initiatives", Initiative, InitiativeIn, InitiativeOut, search=("title", "partner_name"))


# ---- movies (m2m genres/languages)
def _movie_hook(db, m: Movie, data: dict):
    if "genre_ids" in data:
        m.genres = list(db.scalars(select(Genre).where(Genre.id.in_(data["genre_ids"])))) if data["genre_ids"] else []
    if "language_ids" in data:
        m.languages = list(db.scalars(select(Language).where(Language.id.in_(data["language_ids"])))) if data["language_ids"] else []


crud("movies", Movie, MovieIn, MovieOut, search=("title",), hook=_movie_hook, slug_from="title")


def _video_hook(db, v: Video, data: dict):
    if "genre_ids" in data:
        v.genres = list(db.scalars(select(Genre).where(Genre.id.in_(data["genre_ids"])))) if data["genre_ids"] else []


crud("videos", Video, VideoIn, VideoOut, search=("title",), hook=_video_hook, slug_from="title")


# ---- venues & screens
crud("venues", Venue, VenueIn, VenueOut, search=("name", "chain", "address"), order=(Venue.name,))


@router.get("/screens", response_model=Paged[ScreenOut], summary="Screens (optionally per venue)")
def screens(db: DB, page: PageParams, venue_id: int | None = None):
    q = select(Screen).order_by(Screen.venue_id, Screen.name)
    if venue_id:
        q = q.where(Screen.venue_id == venue_id)
    return paginate(db, q, page)


@router.post("/screens", response_model=ScreenOut, status_code=201, summary="Create a screen and generate its seats")
def create_screen(body: ScreenIn, db: DB):
    if not db.get(Venue, body.venue_id):
        raise not_found("Venue")
    s = Screen(venue_id=body.venue_id, name=body.name, layout=body.layout.model_dump())
    db.add(s)
    db.flush()
    seat_svc.build_seats(db, s)
    db.commit()
    return s


@router.put("/screens/{screen_id}", response_model=ScreenOut, summary="Edit a screen (seats booked or held in a show can't be removed)")
def update_screen(screen_id: int, body: ScreenIn, db: DB):
    s = db.get(Screen, screen_id)
    if not s:
        raise not_found("Screen")
    new_layout = body.layout.model_dump()
    s.name = body.name
    if new_layout != s.layout:
        s.layout = new_layout
        seat_svc.build_seats(db, s, sync_if_shows=True)  # in place when shows exist; 409 only if a booked/held seat would change
    db.commit()
    return s


@router.delete("/screens/{screen_id}", response_model=Msg)
def delete_screen(screen_id: int, db: DB):
    s = db.get(Screen, screen_id)
    if not s:
        raise not_found("Screen")
    db.delete(s)
    db.commit()
    return Msg(message="Deleted")


# ---- shows
@router.get("/shows", response_model=Paged[ShowOut], summary="Shows")
def list_shows(db: DB, page: PageParams, movie_id: int | None = None, screen_id: int | None = None, upcoming: bool = True):
    q = select(Show).order_by(Show.starts_at)
    if movie_id:
        q = q.where(Show.movie_id == movie_id)
    if screen_id:
        q = q.where(Show.screen_id == screen_id)
    if upcoming:
        q = q.where(Show.starts_at > utcnow())
    return paginate(db, q, page)


@router.post("/shows/bulk", status_code=201, summary="Schedule shows for a movie on a screen across dates and times")
def bulk_shows(body: ShowBulkIn, admin: AdminUser, db: DB):
    movie, screen = db.get(Movie, body.movie_id), db.get(Screen, body.screen_id)
    if not movie or not screen or not db.get(Language, body.language_id):
        raise not_found("Movie, screen or language")
    res = scheduling.create_shows(db, screen=screen, movie=movie, language_id=body.language_id, fmt=body.format,
                                  dates=body.dates, times=body.times, prices=body.prices, utc_offset_minutes=body.utc_offset_minutes)
    audit(db, admin, "show.bulk_create", "screen", screen.id, {"created": res["created"], "movie_id": movie.id})
    db.commit()
    return {"created": res["created"], "skipped": res["skipped"]}


@router.post("/shows/{show_id}/cancel", response_model=Msg, summary="Cancel a show and refund its bookings")
def cancel_show(show_id: int, db: DB, admin: AdminUser):
    sh = db.get(Show, show_id)
    if not sh:
        raise not_found("Show")
    sh.status = "cancelled"
    audit(db, admin, "show.cancel", "show", sh.id)
    bookings = db.scalars(select(Booking).where(Booking.show_id == show_id, Booking.status.in_(["confirmed", "pending"]))
                          .with_for_update(of=Booking)).all()
    n = 0
    for b in bookings:
        if b.status == "pending":
            bsvc.release_booking(db, b, "expired")
        else:
            bsvc.cancel_booking(db, b, actor_is_admin=True)
            n += 1
    bsvc.commit(db)
    return Msg(message=f"Show cancelled; {n} bookings refunded")


# ---- events
@router.get("/events", response_model=Paged[EventOut], summary="All events in any status")
def admin_events(db: DB, page: PageParams, status: str | None = None, q: str | None = None, section: str | None = None):
    stmt = select(Event).order_by(Event.id.desc())
    if status:
        stmt = stmt.where(Event.status == status)
    if section:
        stmt = stmt.where(Event.section == section)
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    return paginate(db, stmt, page)


@router.patch("/events/{event_id}", response_model=EventOut, summary="Approve / reject / feature an event")
def patch_event(event_id: int, body: EventAdminPatch, db: DB, admin: AdminUser):
    e = db.get(Event, event_id)
    if not e:
        raise not_found("Event")
    audit(db, admin, "event.update", "event", e.id, body.model_dump(exclude_unset=True))
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    if e.organizer_id and body.status in ("approved", "rejected"):
        notify(db, e.organizer_id, f"Event {body.status}", f"Your event '{e.title}' was {body.status}.", "organizer")
    bsvc.commit(db)
    return e


# ---- users & organizers
@router.get("/users", response_model=Paged[UserOut])
def users(db: DB, page: PageParams, q: str | None = None, role: str | None = None):
    stmt = select(User).order_by(User.id.desc())
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.name.ilike(f"%{q}%")))
    if role:
        stmt = stmt.where(User.role == role)
    return paginate(db, stmt, page)


@router.post("/staff", response_model=UserOut, status_code=201,
             summary="Create a Check-in Staff or Support Agent account (staff accounts are never self-service)")
def create_staff(body: StaffCreateIn, admin: AdminUser, db: DB):
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise conflict("An account with this email already exists", "email_taken")
    u = User(email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password),
             email_verified=True)
    db.add(u)
    db.flush()
    audit(db, admin, "staff.create", "user", u.id, {"role": body.role})
    db.commit()
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, body: AdminUserUpdate, admin: AdminUser, db: DB):
    u = db.get(User, user_id)
    if not u:
        raise not_found("User")
    if u.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise AppError(400, "self_lockout", "You cannot demote or disable your own account")
    changes = body.model_dump(exclude_unset=True)
    audit(db, admin, "user.update", "user", u.id, {"from": {k: getattr(u, k) for k in changes}, "to": changes})
    for k, v in changes.items():
        setattr(u, k, v)
    db.commit()
    return u


@router.get("/organizers", response_model=Paged[OrganizerOut])
def organizers(db: DB, page: PageParams, status: str | None = None):
    q = select(OrganizerProfile).order_by(OrganizerProfile.id.desc())
    if status:
        q = q.where(OrganizerProfile.status == status)
    res = paginate(db, q, page)
    res["items"] = [OrganizerOut.model_validate(p).model_copy(update={"user_email": p.user.email, "user_name": p.user.name})
                    for p in res["items"]]
    return res


@router.patch("/organizers/{profile_id}", response_model=OrganizerOut, summary="Approve or reject an organizer application")
def review_organizer(profile_id: int, body: OrganizerReview, db: DB, admin: AdminUser):
    p = db.get(OrganizerProfile, profile_id)
    if not p:
        raise not_found("Organizer")
    p.status, p.reviewed_at = body.status, utcnow()
    audit(db, admin, f"organizer.{body.status}", "organizer", p.id)
    if body.status == "approved" and p.user.role == "user":
        p.user.role = "organizer"
    elif body.status != "approved" and p.user.role == "organizer":
        p.user.role = "user"
    notify(db, p.user_id, f"Organizer application {body.status}",
           f"Your ListYourShow application for {p.company_name} was {body.status}.", "organizer")
    bsvc.commit(db)
    return OrganizerOut.model_validate(p).model_copy(update={"user_email": p.user.email, "user_name": p.user.name})


# ---- bookings & payments
@router.get("/bookings", response_model=Paged[BookingOut])
def all_bookings(db: DB, page: PageParams, status: str | None = None, kind: str | None = None, q: str | None = None):
    stmt = select(Booking).join(User, User.id == Booking.user_id).order_by(Booking.id.desc())
    if status:
        stmt = stmt.where(Booking.status == status)
    if kind:
        stmt = stmt.where(Booking.kind == kind)
    if q:
        stmt = stmt.where(or_(Booking.code.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    res = paginate(db, stmt, page)
    res["items"] = [booking_out(b) for b in res["items"]]
    return res


@router.get("/payments", response_model=Paged[PaymentOut])
def all_payments(db: DB, page: PageParams, status: str | None = None, q: str | None = None):
    stmt = select(Payment).order_by(Payment.id.desc())
    if status:
        stmt = stmt.where(Payment.status == status)
    if q:
        stmt = stmt.where(or_(Payment.order_id.ilike(f"%{q}%"), Payment.payment_id.ilike(f"%{q}%")))
    res = paginate(db, stmt, page)
    res["items"] = [PaymentOut.model_validate(p).model_copy(update={"booking_code": p.booking.code if p.booking else None})
                    for p in res["items"]]
    return res


@router.get("/gift-cards", response_model=Paged[GiftCardOut])
def all_gift_cards(db: DB, page: PageParams):
    return paginate(db, select(GiftCard).order_by(GiftCard.id.desc()), page)


# ---- support
@router.get("/support", response_model=Paged[SupportOut])
def support(db: DB, page: PageParams, status: str | None = None):
    q = select(SupportTicket).order_by(SupportTicket.id.desc())
    if status:
        q = q.where(SupportTicket.status == status)
    return paginate(db, q, page)


@router.patch("/support/{ticket_id}", response_model=SupportOut, summary="Reply to / update a support ticket")
def reply_support(ticket_id: int, body: SupportAdminPatch, db: DB, admin: AdminUser):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise not_found("Ticket")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t, k, v)
    if body.status:
        t.resolved_at = utcnow() if body.status == "resolved" else None
    if body.admin_reply:
        db.add(SupportMessage(ticket_id=t.id, author_id=admin.id, author_role="admin", body=body.admin_reply))
        if t.user_id:
            notify(db, t.user_id, f"Support replied: {t.subject}", body.admin_reply, "support")
    audit(db, admin, "support.update", "support_ticket", t.id, {k: v for k, v in changes.items() if k != "admin_reply"})
    bsvc.commit(db)
    return t


@router.get("/newsletter", summary="Newsletter subscribers")
def newsletter(db: DB, page: PageParams):
    res = paginate(db, select(NewsletterSubscriber).order_by(NewsletterSubscriber.id.desc()), page)
    res["items"] = [{"id": s.id, "email": s.email, "created_at": s.created_at} for s in res["items"]]
    return res


# ---- reports
@router.get("/reports/summary", summary="Business KPIs and trends")
def report(db: DB, days: int = Query(30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    ok = Booking.status == "confirmed"
    totals = db.execute(
        select(func.count(Booking.id), func.coalesce(func.sum(Booking.total_paise), 0),
               func.coalesce(func.sum(Booking.fee_paise + Booking.tax_paise), 0))
        .where(ok, Booking.confirmed_at >= since)
    ).one()
    day = func.date_trunc("day", Booking.confirmed_at)
    daily = db.execute(
        select(day, func.count(Booking.id), func.sum(Booking.total_paise)).where(ok, Booking.confirmed_at >= since)
        .group_by(day).order_by(day)
    ).all()
    by_status = dict(db.execute(select(Booking.status, func.count()).group_by(Booking.status)).all())
    by_kind = db.execute(
        select(Booking.kind, func.count(), func.coalesce(func.sum(Booking.total_paise), 0)).where(ok, Booking.confirmed_at >= since)
        .group_by(Booking.kind)
    ).all()
    top_movies = db.execute(
        select(Movie.title, func.count(Booking.id), func.sum(Booking.total_paise))
        .join(Show, Show.id == Booking.show_id).join(Movie, Movie.id == Show.movie_id)
        .where(ok, Booking.confirmed_at >= since).group_by(Movie.title).order_by(func.sum(Booking.total_paise).desc()).limit(5)
    ).all()
    top_cities = db.execute(
        select(City.name, func.count(Booking.id), func.sum(Booking.total_paise))
        .join(Show, Show.id == Booking.show_id).join(Screen, Screen.id == Show.screen_id)
        .join(Venue, Venue.id == Screen.venue_id).join(City, City.id == Venue.city_id)
        .where(ok, Booking.confirmed_at >= since).group_by(City.name).order_by(func.sum(Booking.total_paise).desc()).limit(5)
    ).all()
    pay_status = dict(db.execute(select(Payment.status, func.count()).group_by(Payment.status)).all())
    counts = {
        "users": db.scalar(select(func.count()).select_from(User)),
        "movies": db.scalar(select(func.count()).select_from(Movie)),
        "venues": db.scalar(select(func.count()).select_from(Venue)),
        "events": db.scalar(select(func.count()).select_from(Event)),
        "pending_events": db.scalar(select(func.count()).select_from(Event).where(Event.status == "pending")),
        "pending_organizers": db.scalar(select(func.count()).select_from(OrganizerProfile).where(OrganizerProfile.status == "pending")),
        "open_tickets": db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "open")),
    }
    return {
        "days": days, "bookings": totals[0], "gross_paise": int(totals[1]), "fees_paise": int(totals[2]),
        "daily": [{"date": d.date().isoformat(), "bookings": c, "gross_paise": int(g or 0)} for d, c, g in daily],
        "by_status": by_status, "payments_by_status": pay_status, "counts": counts,
        "by_kind": [{"kind": k, "bookings": c, "gross_paise": int(g)} for k, c, g in by_kind],
        "top_movies": [{"title": t, "bookings": c, "gross_paise": int(g)} for t, c, g in top_movies],
        "top_cities": [{"city": t, "bookings": c, "gross_paise": int(g)} for t, c, g in top_cities],
    }
