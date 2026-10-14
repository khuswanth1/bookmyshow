"""Theater-vendor portal. Every query is scoped to the caller's VendorProfile: vendors can only ever see or change their own
theaters, screens, shows, bookings and financial records (foreign ids answer 404, never 403, to avoid leaking existence)."""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select, update

from app.core.deps import CurrentUser, DB, PageParams, paginate, require_roles
from app.core.errors import AppError, forbidden, not_found
from app.models import (
    Booking, BookingItem, Language, Movie, MovieRequest, Payout, Screen, Seat, Show, ShowSeat, User, VendorProfile,
    VendorStaff, Venue,
)
from app.routers.bookings import booking_out
from app.schemas import Msg, Paged, ShowBulkIn
from app.schemas_vendor import (
    CancelIn, MovieRequestIn, MovieRequestOut, PayoutOut, PayoutRequestIn, SeatAdminOut, SeatBlockIn, ShowPricesIn,
    ShowSeatBlockIn, TheaterIn, TheaterOut, VendorBookingOut, VendorOut, VendorRegisterIn, VendorScreenIn,
    VendorScreenOut, VendorShowOut,
)
from app.services import booking as bsvc
from app.services import scheduling
from app.services import seats as seat_svc
from app.services.notify import notify
from app.services.platform import audit, get_settings
from app.services.realtime import publish_seats
from app.services.seats import utcnow

router = APIRouter(prefix="/vendor", tags=["Theater Vendor Portal"])

VendorUser = Annotated[User, Depends(require_roles("vendor"))]
# Managers may use only the scheduling / pricing / seat-blocking endpoints, and only on their assigned theaters.
VendorOrManager = Annotated[User, Depends(require_roles("vendor", "manager"))]


def notify_admins(db, title: str, body: str) -> None:
    for aid in db.scalars(select(User.id).where(User.role == "admin", User.is_active)):
        notify(db, aid, title, body, "admin")


def manager_record(db, user: User) -> VendorStaff:
    staff = db.scalar(select(VendorStaff).where(VendorStaff.user_id == user.id))
    if not staff or staff.status != "active":
        raise AppError(403, "staff_inactive", "This staff account is not active")
    return staff


def allowed_theaters(db, user: User) -> set[int] | None:
    """None = unrestricted (the vendor owner). Managers are limited to the theaters the owner assigned."""
    if user.role != "manager":
        return None
    return {t.venue_id for t in manager_record(db, user).theaters}


def my_profile(db, user: User, *, must_be_approved: bool = True) -> VendorProfile:
    if user.role == "manager":
        staff = manager_record(db, user)
        vp = db.get(VendorProfile, staff.vendor_id)
    else:
        vp = db.scalar(select(VendorProfile).where(VendorProfile.user_id == user.id))
    if not vp:
        raise forbidden("No vendor profile")
    if must_be_approved and vp.status != "approved":
        raise AppError(403, "vendor_not_approved", f"Your vendor account is {vp.status}")
    return vp


def own_theater(db, vp: VendorProfile, theater_id: int, allowed: set[int] | None = None) -> Venue:
    v = db.get(Venue, theater_id)
    if not v or v.vendor_id != vp.id or v.type != "cinema" or (allowed is not None and v.id not in allowed):
        raise not_found("Theater")
    return v


def own_screen(db, vp: VendorProfile, screen_id: int, allowed: set[int] | None = None) -> Screen:
    s = db.get(Screen, screen_id)
    if not s or s.venue.vendor_id != vp.id or (allowed is not None and s.venue_id not in allowed):
        raise not_found("Screen")
    return s


def own_show(db, vp: VendorProfile, show_id: int, allowed: set[int] | None = None) -> Show:
    sh = db.get(Show, show_id)
    if not sh or sh.screen.venue.vendor_id != vp.id or (allowed is not None and sh.screen.venue_id not in allowed):
        raise not_found("Show")
    return sh


def theater_out(db, v: Venue) -> TheaterOut:
    o = TheaterOut.model_validate(v)
    o.screens_count = db.scalar(select(func.count()).select_from(Screen).where(Screen.venue_id == v.id))
    return o


# ------------------------------------------------------------------ registration & profile
@router.post("/register", response_model=VendorOut, status_code=201,
             summary="Apply to become a theater vendor (super-admin verification required)")
def register(body: VendorRegisterIn, user: CurrentUser, db: DB):
    if user.role not in ("user",):
        raise AppError(409, "role_conflict", "Only customer accounts can apply as a vendor")
    if db.scalar(select(VendorProfile.id).where(VendorProfile.user_id == user.id)):
        raise AppError(409, "already_registered", "You have already applied as a vendor")
    vp = VendorProfile(user_id=user.id, **body.model_dump())
    db.add(vp)
    db.flush()
    audit(db, user, "vendor.register", "vendor", vp.id, {"business": vp.business_name})
    notify_admins(db, "New vendor application", f"{vp.business_name} applied to list theaters.")
    bsvc.commit(db)
    return vendor_out(vp)


def vendor_out(vp: VendorProfile) -> VendorOut:
    o = VendorOut.model_validate(vp)
    o.user_email, o.user_name = vp.user.email, vp.user.name
    return o


@router.get("/profile", response_model=VendorOut | None, summary="My vendor application / profile (null if none)")
def profile(user: CurrentUser, db: DB):
    vp = db.scalar(select(VendorProfile).where(VendorProfile.user_id == user.id))
    return vendor_out(vp) if vp else None


# ------------------------------------------------------------------ theaters
@router.get("/theaters", response_model=list[TheaterOut], summary="My theaters in every approval state")
def my_theaters(user: VendorOrManager, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    allowed = allowed_theaters(db, user)
    q = select(Venue).where(Venue.vendor_id == vp.id).order_by(Venue.id.desc())
    if allowed is not None:
        q = q.where(Venue.id.in_(allowed))
    return [theater_out(db, v) for v in db.scalars(q).unique()]


@router.post("/theaters", response_model=TheaterOut, status_code=201, summary="Submit a theater for admin approval")
def create_theater(body: TheaterIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    v = Venue(type="cinema", vendor_id=vp.id, approval_status="pending", submitted_at=utcnow(), **body.model_dump())
    v.chain = v.chain or vp.business_name
    db.add(v)
    db.flush()
    audit(db, user, "theater.submit", "theater", v.id, {"name": v.name})
    notify_admins(db, "Theater awaiting approval", f"{vp.business_name} submitted '{v.name}'.")
    bsvc.commit(db)
    return theater_out(db, v)


@router.patch("/theaters/{theater_id}", response_model=TheaterOut, summary="Edit a theater's details")
def update_theater(theater_id: int, body: TheaterIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    v = own_theater(db, vp, theater_id)
    data = body.model_dump()
    if v.approval_status == "approved" and any(data[k] != getattr(v, k) for k in ("name", "city_id", "address")):
        raise AppError(409, "locked_fields", "Name, city and address of an approved theater can only be changed by support")
    for k, val in data.items():
        setattr(v, k, val)
    audit(db, user, "theater.update", "theater", v.id)
    db.commit()
    return theater_out(db, v)


@router.post("/theaters/{theater_id}/resubmit", response_model=TheaterOut, summary="Resubmit a rejected theater")
def resubmit(theater_id: int, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    v = own_theater(db, vp, theater_id)
    if v.approval_status != "rejected":
        raise AppError(409, "not_rejected", "Only rejected theaters can be resubmitted")
    v.approval_status, v.rejection_reason, v.submitted_at = "pending", None, utcnow()
    audit(db, user, "theater.resubmit", "theater", v.id)
    notify_admins(db, "Theater resubmitted", f"{vp.business_name} resubmitted '{v.name}'.")
    bsvc.commit(db)
    return theater_out(db, v)


@router.delete("/theaters/{theater_id}", response_model=Msg, summary="Delete a theater that has no shows")
def delete_theater(theater_id: int, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    v = own_theater(db, vp, theater_id)
    if db.scalar(select(func.count()).select_from(Show).join(Screen, Screen.id == Show.screen_id).where(Screen.venue_id == v.id)):
        raise AppError(409, "theater_in_use", "This theater has shows; deactivate it instead")
    audit(db, user, "theater.delete", "theater", v.id, {"name": v.name})
    db.delete(v)
    db.commit()
    return Msg(message="Deleted")


# ------------------------------------------------------------------ screens & seats
def require_approved_theater(v: Venue) -> None:
    if v.approval_status != "approved":
        raise AppError(409, "theater_not_approved", "Screens and shows can be added once the theater is approved")


def screen_out(db, s: Screen) -> VendorScreenOut:
    o = VendorScreenOut.model_validate(s)
    o.seats = db.scalar(select(func.count()).select_from(Seat).where(Seat.screen_id == s.id))
    o.blocked = db.scalar(select(func.count()).select_from(Seat).where(Seat.screen_id == s.id, Seat.is_blocked))
    o.upcoming_shows = db.scalar(select(func.count()).select_from(Show).where(Show.screen_id == s.id, Show.starts_at > utcnow(), Show.status == "active"))
    return o


@router.get("/theaters/{theater_id}/screens", response_model=list[VendorScreenOut])
def list_screens(theater_id: int, user: VendorOrManager, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    v = own_theater(db, vp, theater_id, allowed_theaters(db, user))
    return [screen_out(db, s) for s in db.scalars(select(Screen).where(Screen.venue_id == v.id).order_by(Screen.name))]


@router.post("/theaters/{theater_id}/screens", response_model=VendorScreenOut, status_code=201,
             summary="Add a screen with a configurable seat layout (Silver/Gold/Platinum…)")
def create_screen(theater_id: int, body: VendorScreenIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    v = own_theater(db, vp, theater_id)
    require_approved_theater(v)
    if db.scalar(select(Screen.id).where(Screen.venue_id == v.id, Screen.name == body.name)):
        raise AppError(409, "duplicate_screen", "A screen with this name already exists")
    s = Screen(venue_id=v.id, name=body.name, status=body.status, layout=body.layout.model_dump())
    db.add(s)
    db.flush()
    n = seat_svc.build_seats(db, s)
    audit(db, user, "screen.create", "screen", s.id, {"theater_id": v.id, "seats": n})
    db.commit()
    return screen_out(db, s)


@router.put("/screens/{screen_id}", response_model=VendorScreenOut, summary="Edit a screen (seats booked or held in a show can't be removed)")
def update_screen(screen_id: int, body: VendorScreenIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    s = own_screen(db, vp, screen_id)
    new_layout = body.layout.model_dump()
    s.name, s.status = body.name, body.status
    if new_layout != s.layout:
        s.layout = new_layout
        seat_svc.build_seats(db, s, sync_if_shows=True)  # in place when shows exist; 409 only if a booked/held seat would change
    audit(db, user, "screen.update", "screen", s.id)
    db.commit()
    return screen_out(db, s)


@router.delete("/screens/{screen_id}", response_model=Msg)
def delete_screen(screen_id: int, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    s = own_screen(db, vp, screen_id)
    if db.scalar(select(func.count()).select_from(Show).where(Show.screen_id == s.id)):
        raise AppError(409, "screen_in_use", "This screen has shows")
    audit(db, user, "screen.delete", "screen", s.id)
    db.delete(s)
    db.commit()
    return Msg(message="Deleted")


@router.get("/screens/{screen_id}/seats", response_model=list[SeatAdminOut], summary="Physical seats incl. maintenance flags")
def screen_seats(screen_id: int, user: VendorOrManager, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    s = own_screen(db, vp, screen_id, allowed_theaters(db, user))
    rows = db.scalars(select(Seat).where(Seat.screen_id == s.id).order_by(Seat.row_index, Seat.number)).all()
    return [SeatAdminOut(id=r.id, row=r.row_label, number=r.number, category=r.category, is_blocked=r.is_blocked, block_reason=r.block_reason) for r in rows]


@router.post("/screens/{screen_id}/seats/block", response_model=Msg,
             summary="Mark seats as blocked for maintenance (or unblock). Applies to all upcoming shows")
def block_seats(screen_id: int, body: SeatBlockIn, user: VendorOrManager, db: DB):
    vp = my_profile(db, user)
    s = own_screen(db, vp, screen_id, allowed_theaters(db, user))
    seats = db.scalars(select(Seat).where(Seat.screen_id == s.id, Seat.id.in_(body.seat_ids)).with_for_update()).all()
    if len(seats) != len(set(body.seat_ids)):
        raise not_found("Seat")
    for st in seats:
        st.is_blocked, st.block_reason = body.blocked, (body.reason if body.blocked else None)
    rows = db.scalars(
        select(ShowSeat).join(Show, Show.id == ShowSeat.show_id)
        .where(Show.screen_id == s.id, Show.starts_at > utcnow(), ShowSeat.seat_id.in_([x.id for x in seats]),
               ShowSeat.status == ("available" if body.blocked else "blocked"))
        .order_by(ShowSeat.id).with_for_update()
    ).all()
    grouped: dict[int, list] = {}
    for r in rows:
        r.status = "blocked" if body.blocked else "available"
        grouped.setdefault(r.show_id, []).append({"id": r.id, "status": r.status})
    audit(db, user, "seat.block" if body.blocked else "seat.unblock", "screen", s.id, {"seats": len(seats), "reason": body.reason})
    db.commit()
    seat_svc.publish_grouped(grouped)
    return Msg(message=f"{len(seats)} seat(s) {'blocked' if body.blocked else 'unblocked'}")


# ------------------------------------------------------------------ shows
def show_stats(db, show_ids: list[int]) -> dict[int, dict]:
    if not show_ids:
        return {}
    rows = db.execute(
        select(ShowSeat.show_id,
               func.count(),
               func.count().filter(ShowSeat.status == "booked"),
               func.count().filter(ShowSeat.status == "blocked"),
               func.count().filter((ShowSeat.status == "locked") & (ShowSeat.locked_until > utcnow())),
               func.coalesce(func.sum(ShowSeat.price_paise).filter(ShowSeat.status == "booked"), 0))
        .where(ShowSeat.show_id.in_(show_ids)).group_by(ShowSeat.show_id)
    ).all()
    return {r[0]: dict(total=r[1], booked=r[2], blocked=r[3], locked=r[4], revenue_paise=int(r[5])) for r in rows}


def show_row(sh: Show, st: dict) -> VendorShowOut:
    return VendorShowOut(
        id=sh.id, screen_id=sh.screen_id, movie_id=sh.movie_id, language_id=sh.language_id, format=sh.format,
        starts_at=sh.starts_at, ends_at=sh.ends_at, prices=sh.prices, status=sh.status, approval_status=sh.approval_status,
        movie_title=sh.movie.title, screen_name=sh.screen.name, theater_id=sh.screen.venue_id,
        theater_name=sh.screen.venue.name, language_name=sh.language.name, **st,
    )


@router.get("/shows", response_model=Paged[VendorShowOut], summary="My shows with occupancy")
def my_shows(user: VendorOrManager, db: DB, page: PageParams, theater_id: int | None = None, screen_id: int | None = None,
             movie_id: int | None = None, upcoming: bool = True):
    vp = my_profile(db, user, must_be_approved=False)
    allowed = allowed_theaters(db, user)
    q = (select(Show).join(Screen, Screen.id == Show.screen_id).join(Venue, Venue.id == Screen.venue_id)
         .where(Venue.vendor_id == vp.id).order_by(Show.starts_at if upcoming else Show.starts_at.desc()))
    if allowed is not None:
        q = q.where(Venue.id.in_(allowed))
    if theater_id:
        q = q.where(Venue.id == theater_id)
    if screen_id:
        q = q.where(Screen.id == screen_id)
    if movie_id:
        q = q.where(Show.movie_id == movie_id)
    q = q.where(Show.starts_at > utcnow()) if upcoming else q.where(Show.starts_at <= utcnow())
    res = paginate(db, q, page)
    stats = show_stats(db, [s.id for s in res["items"]])
    if allowed is not None:  # managers see occupancy, never revenue
        for st in stats.values():
            st["revenue_paise"] = 0
    res["items"] = [show_row(s, stats.get(s.id, {})) for s in res["items"]]
    return res


@router.post("/shows/bulk", status_code=201, summary="Schedule a movie on one of my screens across dates and times")
def bulk_shows(body: ShowBulkIn, user: VendorOrManager, db: DB):
    vp = my_profile(db, user)
    screen = own_screen(db, vp, body.screen_id, allowed_theaters(db, user))
    require_approved_theater(screen.venue)
    if screen.status != "active":
        raise AppError(409, "screen_maintenance", "This screen is under maintenance")
    movie = db.get(Movie, body.movie_id)
    if not movie or not movie.is_active or not db.get(Language, body.language_id):
        raise not_found("Movie or language")
    status = "pending" if get_settings(db)["require_show_approval"] else "approved"
    res = scheduling.create_shows(db, screen=screen, movie=movie, language_id=body.language_id, fmt=body.format, dates=body.dates,
                                  times=body.times, prices=body.prices, utc_offset_minutes=body.utc_offset_minutes, approval_status=status)
    audit(db, user, "show.bulk_create", "screen", screen.id, {"created": res["created"], "movie_id": movie.id, "approval": status})
    if status == "pending" and res["created"]:
        notify_admins(db, "Shows awaiting review", f"{vp.business_name} scheduled {res['created']} show(s) of {movie.title}.")
    bsvc.commit(db)
    return {"created": res["created"], "skipped": res["skipped"], "approval_status": status}


@router.post("/shows/{show_id}/cancel", response_model=Msg, summary="Cancel a show and refund all its bookings")
def cancel_show(show_id: int, user: VendorUser, db: DB, body: CancelIn | None = None):
    vp = my_profile(db, user)
    sh = own_show(db, vp, show_id)
    if sh.status == "cancelled":
        raise AppError(409, "already_cancelled", "Show is already cancelled")
    sh.status = "cancelled"
    refunded = 0
    for b in db.scalars(select(Booking).where(Booking.show_id == sh.id, Booking.status.in_(["confirmed", "pending"])).with_for_update(of=Booking)):
        if b.status == "pending":
            bsvc.release_booking(db, b, "expired")
        else:
            bsvc.cancel_booking(db, b, actor_is_admin=True)
            refunded += 1
    audit(db, user, "show.cancel", "show", sh.id, {"refunded_bookings": refunded, "reason": body.reason if body else None})
    bsvc.commit(db)
    return Msg(message=f"Show cancelled; {refunded} booking(s) refunded")


@router.patch("/shows/{show_id}/prices", response_model=Msg, summary="Change ticket prices for unsold seats of an upcoming show")
def update_prices(show_id: int, body: ShowPricesIn, user: VendorOrManager, db: DB):
    vp = my_profile(db, user)
    sh = own_show(db, vp, show_id, allowed_theaters(db, user))
    if sh.starts_at <= utcnow():
        raise AppError(409, "show_started", "Prices cannot change after the show starts")
    if set(body.prices) != set(sh.prices) or any(p <= 0 for p in body.prices.values()):
        raise AppError(400, "prices_mismatch", f"Provide positive prices for exactly: {sorted(sh.prices)}")
    old = dict(sh.prices)
    sh.prices = body.prices
    for cat, price in body.prices.items():  # booked seats keep the price they were sold at
        db.execute(update(ShowSeat).where(ShowSeat.show_id == sh.id, ShowSeat.category == cat, ShowSeat.status != "booked",
                                          ShowSeat.booking_id.is_(None)).values(price_paise=price))
    audit(db, user, "show.price_update", "show", sh.id, {"from": old, "to": body.prices})
    db.commit()
    return Msg(message="Prices updated for unsold seats")


@router.post("/shows/{show_id}/seats/block", response_model=Msg, summary="Block/unblock individual seats for a single show")
def block_show_seats(show_id: int, body: ShowSeatBlockIn, user: VendorOrManager, db: DB):
    vp = my_profile(db, user)
    sh = own_show(db, vp, show_id, allowed_theaters(db, user))
    rows = db.scalars(select(ShowSeat).where(ShowSeat.show_id == sh.id, ShowSeat.id.in_(body.show_seat_ids)).order_by(ShowSeat.id).with_for_update()).all()
    if len(rows) != len(set(body.show_seat_ids)):
        raise not_found("Seat")
    changes = []
    now = utcnow()
    for r in rows:
        live_hold = r.status == "locked" and r.locked_until and r.locked_until > now
        if body.blocked and (r.status == "available" or (r.status == "locked" and not live_hold)):
            r.status, r.locked_by, r.locked_until = "blocked", None, None
            changes.append({"id": r.id, "status": "blocked"})
        elif not body.blocked and r.status == "blocked":
            r.status = "available"
            changes.append({"id": r.id, "status": "available"})
    audit(db, user, "show.seat_block" if body.blocked else "show.seat_unblock", "show", sh.id, {"changed": len(changes)})
    db.commit()
    publish_seats(sh.id, changes)
    return Msg(message=f"{len(changes)} seat(s) updated (booked or currently held seats are left untouched)")


@router.get("/shows/{show_id}/seats", summary="Seat-level occupancy of one of my shows")
def show_seat_map(show_id: int, user: VendorOrManager, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    sh = own_show(db, vp, show_id, allowed_theaters(db, user))
    return {"show_id": sh.id, "seats": seat_svc.seat_map(db, sh.id, None), "layout": sh.screen.layout}


# ------------------------------------------------------------------ bookings
def _vendor_bookings_query(vp: VendorProfile):
    return (select(Booking).join(Show, Show.id == Booking.show_id).join(Screen, Screen.id == Show.screen_id)
            .join(Venue, Venue.id == Screen.venue_id).where(Venue.vendor_id == vp.id, Booking.status.in_(["confirmed", "cancelled"])))


def vendor_booking_out(b: Booking) -> VendorBookingOut:
    base = booking_out(b)
    return VendorBookingOut(**base.model_dump(), customer_name=b.user.name, theater=b.show.screen.venue.name,
                            commission_paise=b.commission_paise, vendor_share_paise=b.vendor_share_paise)


@router.get("/bookings", response_model=Paged[VendorBookingOut], summary="Bookings at my theaters")
def my_bookings(user: VendorUser, db: DB, page: PageParams, status: Literal["confirmed", "cancelled"] | None = None,
                theater_id: int | None = None, show_id: int | None = None):
    vp = my_profile(db, user, must_be_approved=False)
    q = _vendor_bookings_query(vp).order_by(Booking.created_at.desc())
    if status:
        q = q.where(Booking.status == status)
    if theater_id:
        q = q.where(Venue.id == theater_id)
    if show_id:
        q = q.where(Show.id == show_id)
    res = paginate(db, q, page)
    res["items"] = [vendor_booking_out(b) for b in res["items"]]
    return res


@router.post("/bookings/{booking_id}/cancel", response_model=VendorBookingOut, summary="Cancel a booking at my theater and refund the customer")
def cancel_booking(booking_id: int, user: VendorUser, db: DB, body: CancelIn | None = None):
    vp = my_profile(db, user)
    b = db.scalar(_vendor_bookings_query(vp).where(Booking.id == booking_id).with_for_update(of=Booking))
    if not b:
        raise not_found("Booking")
    bsvc.cancel_booking(db, b, actor_is_admin=True)
    audit(db, user, "booking.vendor_cancel", "booking", b.id, {"code": b.code, "reason": body.reason if body else None})
    bsvc.commit(db)
    return vendor_booking_out(b)


# ------------------------------------------------------------------ money
def earnings_summary(db, vp: VendorProfile) -> dict:
    s = get_settings(db)
    ok = [Booking.vendor_id == vp.id, Booking.status == "confirmed"]
    gross, comm, net = db.execute(
        select(func.coalesce(func.sum(Booking.subtotal_paise - Booking.discount_paise), 0), func.coalesce(func.sum(Booking.commission_paise), 0),
               func.coalesce(func.sum(Booking.vendor_share_paise), 0)).where(*ok)
    ).one()
    cutoff = utcnow() - timedelta(days=s["payout_hold_days"])
    settleable = db.scalar(
        select(func.coalesce(func.sum(Booking.vendor_share_paise), 0)).join(Show, Show.id == Booking.show_id)
        .where(*ok, Show.starts_at <= cutoff)
    )
    paid = db.scalar(select(func.coalesce(func.sum(Payout.amount_paise), 0)).where(Payout.vendor_id == vp.id, Payout.status == "paid"))
    pending = db.scalar(select(func.coalesce(func.sum(Payout.amount_paise), 0)).where(Payout.vendor_id == vp.id, Payout.status == "requested"))
    return {
        "gross_paise": int(gross), "commission_paise": int(comm), "net_paise": int(net), "paid_out_paise": int(paid),
        "pending_payout_paise": int(pending), "available_paise": max(0, int(settleable) - int(paid) - int(pending)),
        "upcoming_paise": int(net) - int(settleable), "commission_pct": float(vp.commission_pct if vp.commission_pct is not None else s["commission_pct"]),
        "min_payout_paise": s["min_payout_paise"], "hold_days": s["payout_hold_days"],
    }


@router.get("/earnings", summary="Revenue, commission, net earnings and withdrawable balance")
def earnings(user: VendorUser, db: DB):
    return earnings_summary(db, my_profile(db, user, must_be_approved=False))


@router.get("/payouts", response_model=Paged[PayoutOut], summary="My payout requests and their status")
def my_payouts(user: VendorUser, db: DB, page: PageParams):
    vp = my_profile(db, user, must_be_approved=False)
    return paginate(db, select(Payout).where(Payout.vendor_id == vp.id).order_by(Payout.id.desc()), page)


@router.post("/payouts", response_model=PayoutOut, status_code=201, summary="Request a payout of available earnings")
def request_payout(body: PayoutRequestIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    db.execute(select(VendorProfile.id).where(VendorProfile.id == vp.id).with_for_update())  # serialise concurrent requests
    e = earnings_summary(db, vp)
    amount = body.amount_paise or e["available_paise"]
    if amount < e["min_payout_paise"]:
        raise AppError(400, "below_minimum", f"Minimum payout is ₹{e['min_payout_paise'] / 100:.0f}")
    if amount > e["available_paise"]:
        raise AppError(400, "insufficient_balance", f"Only ₹{e['available_paise'] / 100:.2f} is available")
    p = Payout(vendor_id=vp.id, amount_paise=amount)
    db.add(p)
    db.flush()
    audit(db, user, "payout.request", "payout", p.id, {"amount_paise": amount})
    notify_admins(db, "Payout requested", f"{vp.business_name} requested ₹{amount / 100:.2f}.")
    bsvc.commit(db)
    return p


@router.get("/analytics", summary="Sales, occupancy and top-movie analytics")
def analytics(user: VendorUser, db: DB, days: int = Query(30, ge=1, le=365), theater_id: int | None = None):
    vp = my_profile(db, user, must_be_approved=False)
    since = utcnow() - timedelta(days=days)
    base = [Booking.vendor_id == vp.id, Booking.status == "confirmed", Booking.confirmed_at >= since]
    join = [(Show, Show.id == Booking.show_id), (Screen, Screen.id == Show.screen_id), (Venue, Venue.id == Screen.venue_id)]
    if theater_id:
        base.append(Venue.id == theater_id)

    def q(*cols):
        s = select(*cols).select_from(Booking)
        for t, on in join:
            s = s.join(t, on)
        return s.where(*base)

    tot = db.execute(q(func.count(Booking.id), func.coalesce(func.sum(Booking.subtotal_paise - Booking.discount_paise), 0),
                       func.coalesce(func.sum(Booking.commission_paise), 0), func.coalesce(func.sum(Booking.vendor_share_paise), 0))).one()
    tickets = db.scalar(
        select(func.coalesce(func.sum(BookingItem.quantity), 0)).join(Booking, Booking.id == BookingItem.booking_id)
        .join(Show, Show.id == Booking.show_id).join(Screen, Screen.id == Show.screen_id).join(Venue, Venue.id == Screen.venue_id).where(*base))
    day = func.date_trunc("day", Booking.confirmed_at)
    daily = db.execute(q(day, func.count(Booking.id), func.sum(Booking.vendor_share_paise)).group_by(day).order_by(day)).all()
    movies = db.execute(q(Movie.title, func.count(Booking.id), func.sum(Booking.vendor_share_paise)).join(Movie, Movie.id == Show.movie_id)
                        .group_by(Movie.title).order_by(func.sum(Booking.vendor_share_paise).desc()).limit(5)).all()
    theaters = db.execute(q(Venue.id, Venue.name, func.count(Booking.id), func.sum(Booking.vendor_share_paise)).group_by(Venue.id, Venue.name)
                          .order_by(func.sum(Booking.vendor_share_paise).desc())).all()
    # occupancy over shows that already started in the period
    occ = db.execute(
        select(func.count(), func.count().filter(ShowSeat.status == "booked")).select_from(ShowSeat)
        .join(Show, Show.id == ShowSeat.show_id).join(Screen, Screen.id == Show.screen_id).join(Venue, Venue.id == Screen.venue_id)
        .where(Venue.vendor_id == vp.id, Show.starts_at >= since, Show.starts_at <= utcnow(), Show.status == "active",
               *( [Venue.id == theater_id] if theater_id else []))
    ).one()
    return {
        "days": days, "bookings": tot[0], "gross_paise": int(tot[1]), "commission_paise": int(tot[2]), "net_paise": int(tot[3]), "tickets": int(tickets),
        "occupancy_pct": round(100 * occ[1] / occ[0], 1) if occ[0] else 0.0,
        "daily": [{"date": d.date().isoformat(), "bookings": c, "net_paise": int(n or 0)} for d, c, n in daily],
        "top_movies": [{"title": t, "bookings": c, "net_paise": int(n or 0)} for t, c, n in movies],
        "theaters": [{"id": i, "name": n, "bookings": c, "net_paise": int(v or 0)} for i, n, c, v in theaters],
    }


def _csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # neutralise spreadsheet formula injection


@router.get("/reports/sales", summary="Sales report (JSON or CSV download)")
def sales_report(user: VendorUser, db: DB, date_from: date | None = None, date_to: date | None = None,
                 theater_id: int | None = None, format: Literal["json", "csv"] = "json"):
    vp = my_profile(db, user, must_be_approved=False)
    q = _vendor_bookings_query(vp).where(Booking.status == "confirmed").order_by(Booking.confirmed_at.desc()).limit(5000)
    if date_from:
        q = q.where(Booking.confirmed_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        q = q.where(Booking.confirmed_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if theater_id:
        q = q.where(Venue.id == theater_id)
    rows = []
    for b in db.scalars(q).unique():
        rows.append({
            "booked_at": b.confirmed_at.isoformat(), "booking_id": b.code, "theater": b.show.screen.venue.name, "screen": b.show.screen.name,
            "movie": b.show.movie.title, "show_time": b.show.starts_at.isoformat(), "seats": ", ".join(i.label for i in b.items),
            "gross": (b.subtotal_paise - b.discount_paise) / 100, "commission": b.commission_paise / 100, "net": b.vendor_share_paise / 100,
        })
    if format == "json":
        return {"rows": rows, "totals": {k: round(sum(r[k] for r in rows), 2) for k in ("gross", "commission", "net")}}
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["booked_at", "booking_id", "theater", "screen", "movie", "show_time", "seats", "gross", "commission", "net"]
    w.writerow(cols)
    for r in rows:
        w.writerow([_csv_safe(r[c]) for c in cols])
    audit(db, user, "report.export", "vendor", vp.id, {"rows": len(rows)})
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sales-report.csv"'})


# ------------------------------------------------------------------ movie requests
@router.post("/movie-requests", response_model=MovieRequestOut, status_code=201, summary="Ask the platform to add a movie")
def request_movie(body: MovieRequestIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    r = MovieRequest(vendor_id=vp.id, **body.model_dump())
    db.add(r)
    db.flush()
    audit(db, user, "movie_request.create", "movie_request", r.id, {"title": r.title})
    notify_admins(db, "Movie request", f"{vp.business_name} requested '{r.title}'.")
    bsvc.commit(db)
    return r


@router.get("/movie-requests", response_model=list[MovieRequestOut])
def my_movie_requests(user: VendorUser, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    return db.scalars(select(MovieRequest).where(MovieRequest.vendor_id == vp.id).order_by(MovieRequest.id.desc())).all()
