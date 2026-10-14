"""Super-admin marketplace controls: approval workflow, commissions, payouts, settings, audit trail, reports."""
import csv
import io
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.core.deps import AdminUser, DB, PageParams, paginate, require_roles
from app.core.errors import AppError, not_found
from app.models import (
    AuditLog, Booking, Movie, MovieRequest, Payment, Payout, Screen, Show, User, VendorProfile, Venue,
)
from app.routers.organizer import unique_slug
from app.routers.vendor import earnings_summary, notify_admins
from app.schemas import Msg, Paged
from app.schemas_vendor import (
    AuditOut, MovieRequestOut, MovieRequestReview, PayoutOut, PayoutProcess, SettingsIn, ShowReview, TheaterOut, TheaterReview,
    VendorOut, VendorReview,
)
from app.services import booking as bsvc
from app.services.notify import notify
from app.services.platform import audit, get_settings, set_setting
from app.services.seats import utcnow

router = APIRouter(prefix="/admin", tags=["Super Admin: Marketplace"], dependencies=[Depends(require_roles("admin"))])


# ------------------------------------------------------------------ vendors
def _vendor_row(db, vp: VendorProfile) -> VendorOut:
    o = VendorOut.model_validate(vp)
    o.user_email, o.user_name = vp.user.email, vp.user.name
    o.theaters = db.scalar(select(func.count()).select_from(Venue).where(Venue.vendor_id == vp.id))
    return o


@router.get("/vendors", response_model=Paged[VendorOut], summary="Vendor applications and accounts")
def vendors(db: DB, page: PageParams, status: str | None = None, q: str | None = None):
    stmt = select(VendorProfile).order_by(VendorProfile.id.desc())
    if status:
        stmt = stmt.where(VendorProfile.status == status)
    if q:
        stmt = stmt.where(VendorProfile.business_name.ilike(f"%{q}%"))
    res = paginate(db, stmt, page)
    res["items"] = [_vendor_row(db, v) for v in res["items"]]
    return res


@router.patch("/vendors/{vendor_id}", response_model=VendorOut, summary="Approve, reject or suspend a vendor (and set its commission)")
def review_vendor(vendor_id: int, body: VendorReview, admin: AdminUser, db: DB):
    vp = db.scalar(select(VendorProfile).where(VendorProfile.id == vendor_id).with_for_update())
    if not vp:
        raise not_found("Vendor")
    if body.status in ("rejected", "suspended") and not body.reason:
        raise AppError(400, "reason_required", "Please give a reason")
    before = vp.status
    vp.status, vp.reviewed_by, vp.reviewed_at = body.status, admin.id, utcnow()
    vp.rejection_reason = body.reason if body.status in ("rejected", "suspended") else None
    if body.commission_pct is not None:
        vp.commission_pct = body.commission_pct
    if body.status == "approved" and vp.user.role == "user":
        vp.user.role = "vendor"
    elif body.status in ("rejected", "pending") and vp.user.role == "vendor":
        vp.user.role = "user"
    # suspended keeps the vendor role (can log in, read-only) but hides every theater publicly (see public_show_conditions)
    audit(db, admin, f"vendor.{body.status}", "vendor", vp.id, {"from": before, "reason": body.reason, "commission_pct": body.commission_pct})
    notify(db, vp.user_id, f"Vendor application {body.status}",
           f"Your vendor account '{vp.business_name}' is now {body.status}." + (f" Reason: {body.reason}" if body.reason else ""), "vendor")
    bsvc.commit(db)
    return _vendor_row(db, vp)


# ------------------------------------------------------------------ theaters
def _theater_row(db, v: Venue) -> TheaterOut:
    o = TheaterOut.model_validate(v)
    o.screens_count = db.scalar(select(func.count()).select_from(Screen).where(Screen.venue_id == v.id))
    if v.vendor_id:
        vp = db.get(VendorProfile, v.vendor_id)
        o.vendor_name = vp.business_name if vp else None
    return o


@router.get("/theaters", response_model=Paged[TheaterOut], summary="All cinemas with approval status")
def theaters(db: DB, page: PageParams, status: str | None = None, vendor_id: int | None = None, q: str | None = None):
    stmt = select(Venue).where(Venue.type == "cinema").order_by((Venue.approval_status == "pending").desc(), Venue.id.desc())
    if status:
        stmt = stmt.where(Venue.approval_status == status)
    if vendor_id:
        stmt = stmt.where(Venue.vendor_id == vendor_id)
    if q:
        stmt = stmt.where(Venue.name.ilike(f"%{q}%"))
    res = paginate(db, stmt, page)
    res["items"] = [_theater_row(db, v) for v in res["items"]]
    return res


@router.patch("/theaters/{theater_id}/review", response_model=TheaterOut, summary="Approve, reject or suspend a theater listing")
def review_theater(theater_id: int, body: TheaterReview, admin: AdminUser, db: DB):
    v = db.get(Venue, theater_id)
    if not v or v.type != "cinema":
        raise not_found("Theater")
    if body.status in ("rejected", "suspended") and not body.reason:
        raise AppError(400, "reason_required", "Please give a reason")
    if body.status == "approved" and v.vendor_id:
        vp = db.get(VendorProfile, v.vendor_id)
        if not vp or vp.status != "approved":
            raise AppError(409, "vendor_not_approved", "Approve the vendor first")
    before = v.approval_status
    v.approval_status, v.reviewed_at = body.status, utcnow()
    v.rejection_reason = body.reason if body.status in ("rejected", "suspended") else None
    audit(db, admin, f"theater.{body.status}", "theater", v.id, {"from": before, "reason": body.reason})
    if v.vendor_id:
        vp = db.get(VendorProfile, v.vendor_id)
        notify(db, vp.user_id, f"Theater {body.status}", f"'{v.name}' is now {body.status}." + (f" Reason: {body.reason}" if body.reason else ""), "vendor")
    bsvc.commit(db)
    return _theater_row(db, v)


# ------------------------------------------------------------------ show listing review (optional moderation)
@router.get("/shows/pending", summary="Vendor shows awaiting review, grouped by theater/movie")
def pending_shows(db: DB):
    rows = db.execute(
        select(Venue.id, Venue.name, Movie.title, func.count(Show.id), func.min(Show.starts_at), func.max(Show.starts_at), func.array_agg(Show.id))
        .join(Screen, Screen.venue_id == Venue.id).join(Show, Show.screen_id == Screen.id).join(Movie, Movie.id == Show.movie_id)
        .where(Show.approval_status == "pending").group_by(Venue.id, Venue.name, Movie.title).order_by(func.min(Show.starts_at))
    ).all()
    return [{"theater_id": a, "theater": b, "movie": c, "shows": d, "first": e, "last": f, "show_ids": ids} for a, b, c, d, e, f, ids in rows]


@router.post("/shows/review", response_model=Msg, summary="Approve or reject pending vendor shows")
def review_shows(body: ShowReview, admin: AdminUser, db: DB):
    shows = db.scalars(select(Show).where(Show.id.in_(body.show_ids), Show.approval_status == "pending").with_for_update(of=Show)).all()
    for s in shows:
        s.approval_status = body.status
        if body.status == "rejected":
            s.status = "cancelled"
    audit(db, admin, f"show.review_{body.status}", "show", None, {"count": len(shows), "ids": body.show_ids[:50]})
    db.commit()
    return Msg(message=f"{len(shows)} show(s) {body.status}")


# ------------------------------------------------------------------ movie requests
@router.get("/movie-requests", response_model=Paged[MovieRequestOut])
def movie_requests(db: DB, page: PageParams, status: str | None = None):
    q = select(MovieRequest).order_by(MovieRequest.id.desc())
    if status:
        q = q.where(MovieRequest.status == status)
    res = paginate(db, q, page)
    res["items"] = [MovieRequestOut.model_validate(r).model_copy(update={"vendor_name": r.vendor.business_name}) for r in res["items"]]
    return res


@router.patch("/movie-requests/{req_id}", response_model=MovieRequestOut, summary="Approve (creates/links the movie) or reject a request")
def review_movie_request(req_id: int, body: MovieRequestReview, admin: AdminUser, db: DB):
    r = db.scalar(select(MovieRequest).where(MovieRequest.id == req_id).with_for_update())
    if not r:
        raise not_found("Request")
    if r.status != "pending":
        raise AppError(409, "already_reviewed", "This request was already reviewed")
    if body.status == "approved":
        if body.movie_id:
            if not db.get(Movie, body.movie_id):
                raise not_found("Movie")
            r.movie_id = body.movie_id
        else:
            from datetime import date
            m = Movie(title=r.title, slug=unique_slug(db, Movie, r.title), synopsis=r.synopsis, duration_min=r.duration_min,
                      certificate=r.certificate, release_date=r.release_date or date.today(), is_active=True)
            db.add(m)
            db.flush()
            r.movie_id = m.id
    r.status, r.admin_note, r.reviewed_at = body.status, body.admin_note, utcnow()
    audit(db, admin, f"movie_request.{body.status}", "movie_request", r.id, {"movie_id": r.movie_id})
    notify(db, r.vendor.user_id, f"Movie request {body.status}", f"'{r.title}' was {body.status}." + (f" {body.admin_note}" if body.admin_note else ""), "vendor")
    bsvc.commit(db)
    return MovieRequestOut.model_validate(r).model_copy(update={"vendor_name": r.vendor.business_name})


# ------------------------------------------------------------------ payouts & commissions
@router.get("/payouts", response_model=Paged[PayoutOut])
def payouts(db: DB, page: PageParams, status: str | None = None, vendor_id: int | None = None):
    q = select(Payout).order_by((Payout.status == "requested").desc(), Payout.id.desc())
    if status:
        q = q.where(Payout.status == status)
    if vendor_id:
        q = q.where(Payout.vendor_id == vendor_id)
    res = paginate(db, q, page)
    res["items"] = [PayoutOut.model_validate(p).model_copy(update={"vendor_name": p.vendor.business_name}) for p in res["items"]]
    return res


@router.patch("/payouts/{payout_id}", response_model=PayoutOut, summary="Mark a payout as paid (with bank reference) or reject it")
def process_payout(payout_id: int, body: PayoutProcess, admin: AdminUser, db: DB):
    p = db.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
    if not p:
        raise not_found("Payout")
    if p.status != "requested":
        raise AppError(409, "already_processed", "This payout was already processed")
    if body.status == "paid" and not body.reference:
        raise AppError(400, "reference_required", "Enter the bank/UTR reference of the transfer")
    p.status, p.reference, p.note, p.processed_by, p.processed_at = body.status, body.reference, body.note, admin.id, utcnow()
    audit(db, admin, f"payout.{body.status}", "payout", p.id, {"amount_paise": p.amount_paise, "vendor_id": p.vendor_id, "reference": body.reference})
    notify(db, p.vendor.user_id, f"Payout {body.status}", f"Your payout of ₹{p.amount_paise / 100:.2f} was {body.status}." + (f" Ref: {body.reference}" if body.reference else ""), "vendor")
    bsvc.commit(db)
    return PayoutOut.model_validate(p).model_copy(update={"vendor_name": p.vendor.business_name})


@router.get("/commissions", summary="Commission earned per vendor")
def commissions(db: DB, days: int = Query(30, ge=1, le=3650)):
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(VendorProfile.id, VendorProfile.business_name, VendorProfile.commission_pct, func.count(Booking.id),
               func.coalesce(func.sum(Booking.subtotal_paise - Booking.discount_paise), 0), func.coalesce(func.sum(Booking.commission_paise), 0),
               func.coalesce(func.sum(Booking.vendor_share_paise), 0))
        .join(Booking, (Booking.vendor_id == VendorProfile.id) & (Booking.status == "confirmed") & (Booking.confirmed_at >= since), isouter=True)
        .group_by(VendorProfile.id).order_by(func.sum(Booking.commission_paise).desc().nullslast())
    ).all()
    s = get_settings(db)
    out = []
    for i, name, pct, n, gross, comm, share in rows:
        paid = db.scalar(select(func.coalesce(func.sum(Payout.amount_paise), 0)).where(Payout.vendor_id == i, Payout.status == "paid"))
        out.append({"vendor_id": i, "vendor": name, "commission_pct": float(pct if pct is not None else s["commission_pct"]), "bookings": n,
                    "gross_paise": int(gross), "commission_paise": int(comm), "vendor_share_paise": int(share), "paid_out_paise": int(paid)})
    return {"days": days, "default_pct": s["commission_pct"], "vendors": out, "total_commission_paise": sum(r["commission_paise"] for r in out)}


# ------------------------------------------------------------------ settings & audit
@router.get("/settings", summary="Platform settings")
def read_settings(db: DB):
    return get_settings(db)


@router.put("/settings", summary="Update platform settings (commission default, show moderation, payout rules)")
def update_settings(body: SettingsIn, admin: AdminUser, db: DB):
    before = get_settings(db)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        set_setting(db, k, v)
    audit(db, admin, "settings.update", "settings", None, {"from": {k: before[k] for k in changes}, "to": changes})
    db.commit()
    return get_settings(db)


@router.get("/audit-logs", response_model=Paged[AuditOut], summary="Append-only audit trail")
def audit_logs(db: DB, page: PageParams, action: str | None = None, actor: str | None = None, entity_type: str | None = None,
               entity_id: str | None = None):
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action.ilike(f"{action}%"))
    if actor:
        q = q.where(AuditLog.actor_email.ilike(f"%{actor}%"))
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    return paginate(db, q, page)


# ------------------------------------------------------------------ reports
@router.get("/reports/marketplace", summary="Marketplace KPIs: approvals, commissions, refunds, bookings")
def marketplace_report(db: DB, days: int = Query(30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    ok = [Booking.status == "confirmed", Booking.confirmed_at >= since]
    b = db.execute(select(func.count(Booking.id), func.coalesce(func.sum(Booking.total_paise), 0), func.coalesce(func.sum(Booking.commission_paise), 0),
                          func.coalesce(func.sum(Booking.fee_paise + Booking.tax_paise), 0)).where(*ok)).one()
    refunds = db.execute(select(func.count(), func.coalesce(func.sum(Payment.refund_paise), 0)).where(Payment.refund_paise > 0, Payment.updated_at >= since)).one()
    cancelled = db.scalar(select(func.count()).select_from(Booking).where(Booking.status == "cancelled", Booking.cancelled_at >= since))
    pending_payout = db.scalar(select(func.coalesce(func.sum(Payout.amount_paise), 0)).where(Payout.status == "requested"))
    paid_payout = db.scalar(select(func.coalesce(func.sum(Payout.amount_paise), 0)).where(Payout.status == "paid"))
    count = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(*w))  # noqa: E731
    day = func.date_trunc("day", Booking.confirmed_at)
    daily = db.execute(select(day, func.count(Booking.id), func.sum(Booking.total_paise), func.sum(Booking.commission_paise)).where(*ok).group_by(day).order_by(day)).all()
    return {
        "days": days, "bookings": b[0], "gross_paise": int(b[1]), "commission_paise": int(b[2]), "fees_paise": int(b[3]),
        "refunds": refunds[0], "refunded_paise": int(refunds[1]), "cancelled_bookings": cancelled,
        "payouts_pending_paise": int(pending_payout), "payouts_paid_paise": int(paid_payout),
        "approvals": {
            "vendors_pending": count(VendorProfile, VendorProfile.status == "pending"), "theaters_pending": count(Venue, Venue.approval_status == "pending", Venue.type == "cinema"),
            "shows_pending": count(Show, Show.approval_status == "pending"), "movie_requests_pending": count(MovieRequest, MovieRequest.status == "pending"),
            "payouts_pending": count(Payout, Payout.status == "requested"),
        },
        "totals": {"vendors": count(VendorProfile, VendorProfile.status == "approved"), "theaters": count(Venue, Venue.approval_status == "approved", Venue.type == "cinema"),
                   "customers": count(User, User.role == "user"), "organizers": count(User, User.role == "organizer")},
        "daily": [{"date": d.date().isoformat(), "bookings": c, "gross_paise": int(g or 0), "commission_paise": int(m or 0)} for d, c, g, m in daily],
    }


def _csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/reports/bookings.csv", summary="Export confirmed bookings as CSV")
def export_bookings(admin: AdminUser, db: DB, days: int = Query(30, ge=1, le=3650)):
    since = utcnow() - timedelta(days=days)
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["confirmed_at", "booking_id", "kind", "title", "customer_email", "total", "commission", "vendor_share", "vendor_id"]
    w.writerow(cols)
    for b in db.scalars(select(Booking).where(Booking.status == "confirmed", Booking.confirmed_at >= since).order_by(Booking.confirmed_at.desc()).limit(20000)):
        title = b.show.movie.title if b.show else (b.event.title if b.event else "")
        w.writerow([_csv_safe(x) for x in (b.confirmed_at.isoformat(), b.code, b.kind, title, b.user.email, b.total_paise / 100,
                                           b.commission_paise / 100, b.vendor_share_paise / 100, b.vendor_id)])
    audit(db, admin, "report.export", "bookings", None, {"days": days})
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="bookings.csv"'})


@router.get("/vendors/{vendor_id}/earnings", summary="A vendor's earnings summary (as the vendor sees it)")
def vendor_earnings(vendor_id: int, db: DB):
    vp = db.get(VendorProfile, vendor_id)
    if not vp:
        raise not_found("Vendor")
    return earnings_summary(db, vp)
