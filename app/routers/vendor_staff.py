"""Theater managers: created by an approved vendor, activated by a super admin, limited to assigned theaters."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.deps import DB, PageParams, paginate, require_roles
from app.core.errors import AppError, conflict, not_found
from app.core.security import hash_password
from app.models import User, VendorProfile, VendorStaff, VendorStaffTheater, Venue
from app.routers.vendor import VendorOrManager, VendorUser, my_profile, notify_admins, allowed_theaters
from app.schemas import Msg, Paged
from app.schemas_vendor import ManagerCreateIn, ManagerOut, ManagerPatchIn, StaffReviewIn
from app.services.notify import notify
from app.services.platform import audit
from app.services.seats import utcnow

router = APIRouter(prefix="/vendor", tags=["Theater Vendor Portal"])
admin_router = APIRouter(prefix="/admin", tags=["Admin Panel"], dependencies=[Depends(require_roles("admin"))])
Admin = Annotated[User, Depends(require_roles("admin"))]


def _out(db, s: VendorStaff) -> ManagerOut:
    names = dict(db.execute(select(Venue.id, Venue.name).where(Venue.id.in_([t.venue_id for t in s.theaters]))).all()) if s.theaters else {}
    ids = sorted(t.venue_id for t in s.theaters)
    return ManagerOut(id=s.id, user_id=s.user_id, name=s.user.name, email=s.user.email, status=s.status,
                      rejection_reason=s.rejection_reason, theater_ids=ids, theater_names=[names.get(i, "") for i in ids],
                      created_at=s.created_at)


def _own_theater_ids(db, vp: VendorProfile, ids: list[int]) -> list[int]:
    ids = sorted(set(ids))
    ok = set(db.scalars(select(Venue.id).where(Venue.id.in_(ids), Venue.vendor_id == vp.id, Venue.type == "cinema")))
    if ok != set(ids):  # an id that is not yours looks exactly like one that does not exist
        raise not_found("Theater")
    return ids


def _own_staff(db, vp: VendorProfile, staff_id: int) -> VendorStaff:
    s = db.get(VendorStaff, staff_id)
    if not s or s.vendor_id != vp.id:
        raise not_found("Staff member")
    return s


# ------------------------------------------------------------------ vendor side
@router.get("/me", summary="Who am I in the vendor portal (owner or manager) and what can I reach")
def me(user: VendorOrManager, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    allowed = allowed_theaters(db, user)
    q = select(Venue.id, Venue.name).where(Venue.vendor_id == vp.id, Venue.type == "cinema").order_by(Venue.name)
    if allowed is not None:
        q = q.where(Venue.id.in_(allowed))
    return {"role": user.role, "business_name": vp.business_name, "vendor_status": vp.status,
            "theaters": [{"id": i, "name": n} for i, n in db.execute(q).all()]}


@router.get("/staff", response_model=list[ManagerOut], summary="My theater managers")
def list_staff(user: VendorUser, db: DB):
    vp = my_profile(db, user, must_be_approved=False)
    rows = db.scalars(select(VendorStaff).where(VendorStaff.vendor_id == vp.id).order_by(VendorStaff.id.desc())).unique().all()
    return [_out(db, s) for s in rows]


@router.post("/staff", response_model=ManagerOut, status_code=201,
             summary="Create a theater manager. The account stays inactive until a super admin approves it")
def create_staff(body: ManagerCreateIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    ids = _own_theater_ids(db, vp, body.theater_ids)
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise conflict("An account with this email already exists", "email_taken")
    u = User(email=email, name=body.name.strip(), role="manager", password_hash=hash_password(body.password), is_active=False)
    db.add(u)
    db.flush()
    s = VendorStaff(user_id=u.id, vendor_id=vp.id, created_by_id=user.id)
    s.theaters = [VendorStaffTheater(venue_id=i) for i in ids]
    db.add(s)
    db.flush()
    audit(db, user, "vendor_staff.create", "user", u.id, {"theaters": ids})
    notify_admins(db, "Theater manager awaiting approval", f"{vp.business_name} added {u.name} ({u.email}) as a manager.")
    db.commit()
    db.refresh(s)
    return _out(db, s)


@router.patch("/staff/{staff_id}", response_model=ManagerOut, summary="Change a manager's theaters, or disable / re-enable them")
def update_staff(staff_id: int, body: ManagerPatchIn, user: VendorUser, db: DB):
    vp = my_profile(db, user)
    s = _own_staff(db, vp, staff_id)
    if body.theater_ids is not None:
        ids = _own_theater_ids(db, vp, body.theater_ids)
        s.theaters.clear()
        db.flush()
        s.theaters.extend(VendorStaffTheater(venue_id=i) for i in ids)
        audit(db, user, "vendor_staff.theaters", "user", s.user_id, {"theaters": ids})
    if body.disabled is not None:
        if body.disabled and s.status == "active":
            s.status, s.user.is_active = "disabled", False
        elif not body.disabled and s.status == "disabled":  # only an account an admin once approved can come back
            s.status, s.user.is_active = "active", True
        elif s.status in ("pending", "rejected"):
            raise AppError(409, "not_reviewed", "This account has not been approved by an admin")
        audit(db, user, "vendor_staff.disable" if body.disabled else "vendor_staff.enable", "user", s.user_id)
    db.commit()
    db.refresh(s)
    return _out(db, s)


# ------------------------------------------------------------------ admin side
@admin_router.get("/vendor-staff", response_model=Paged[ManagerOut], summary="Manager accounts created by vendors")
def admin_list(db: DB, page: PageParams, status: str | None = None):
    q = select(VendorStaff).order_by(VendorStaff.id.desc())
    if status:
        q = q.where(VendorStaff.status == status)
    res = paginate(db, q, page)
    res["items"] = [_admin_row(db, s) for s in res["items"]]
    return res


def _admin_row(db, s: VendorStaff) -> dict:
    return {**_out(db, s).model_dump(), "vendor": db.get(VendorProfile, s.vendor_id).business_name}


@admin_router.patch("/vendor-staff/{staff_id}", summary="Approve or reject a manager account")
def admin_review(staff_id: int, body: StaffReviewIn, admin: Admin, db: DB):
    s = db.get(VendorStaff, staff_id)
    if not s:
        raise not_found("Staff member")
    if s.status != "pending":
        raise AppError(409, "already_reviewed", f"This account is already {s.status}")
    if body.status == "rejected" and not (body.reason or "").strip():
        raise AppError(400, "reason_required", "Give a reason when rejecting")
    s.reviewed_at = utcnow()
    if body.status == "approved":
        s.status, s.user.is_active, s.user.email_verified = "active", True, True
    else:
        s.status, s.rejection_reason = "rejected", body.reason.strip()
    audit(db, admin, f"vendor_staff.{body.status}", "user", s.user_id, {"vendor_id": s.vendor_id, "reason": body.reason})
    vendor_user = db.get(VendorProfile, s.vendor_id).user_id
    notify(db, vendor_user, f"Manager {body.status}: {s.user.name}",
           "They can sign in now." if body.status == "approved" else f"Reason: {body.reason}", "vendor")
    db.commit()
    db.refresh(s)
    return _admin_row(db, s)
