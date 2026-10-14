"""Platform settings, audit logging and the shared visibility rules for vendor-owned inventory."""
from contextvars import ContextVar

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AuditLog, PlatformSetting, Show, User, VendorProfile, Venue

client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)

DEFAULT_SETTINGS = {
    "commission_pct": 10.0,        # platform commission on net ticket value at vendor theaters
    "require_show_approval": False,  # admin reviews every new vendor show before it goes public
    "payout_hold_days": 0,          # earnings become withdrawable this many days after the show starts
    "min_payout_paise": 100_00,
}


def get_settings(db: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in db.scalars(select(PlatformSetting)):
        out[row.key] = row.value.get("v") if isinstance(row.value, dict) else row.value
    return out


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(PlatformSetting, key)
    if row:
        row.value = {"v": value}
    else:
        db.add(PlatformSetting(key=key, value={"v": value}))


def audit(db: Session, actor: User | None, action: str, entity_type: str | None = None, entity_id=None,
          meta: dict | None = None, *, actor_email: str | None = None) -> None:
    """Append-only audit trail. Written in the caller's transaction so it commits/rolls back with the change."""
    db.add(AuditLog(
        actor_id=actor.id if actor else None, actor_email=(actor.email if actor else actor_email),
        actor_role=actor.role if actor else None, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, meta=meta or None, ip=client_ip.get(),
    ))


# --------------------------------------------------------------------- public visibility
def public_show_conditions():
    """SQL conditions a Show/Venue pair must satisfy to be visible or bookable by customers.

    Unapproved vendors, unapproved/suspended theaters and (when moderation is on) unreviewed shows never appear publicly.
    Requires Show and Venue to be joined in the query.
    """
    approved_vendors = select(VendorProfile.id).where(VendorProfile.status == "approved")
    return [
        Show.status == "active",
        Show.approval_status == "approved",
        Venue.is_active,
        Venue.approval_status == "approved",
        or_(Venue.vendor_id.is_(None), Venue.vendor_id.in_(approved_vendors)),
    ]


def public_venue_conditions():
    approved_vendors = select(VendorProfile.id).where(VendorProfile.status == "approved")
    return [Venue.approval_status == "approved", or_(Venue.vendor_id.is_(None), Venue.vendor_id.in_(approved_vendors))]


def venue_is_public(db: Session, venue: Venue) -> bool:
    if not venue.is_active or venue.approval_status != "approved":
        return False
    if venue.vendor_id is None:
        return True
    vp = db.get(VendorProfile, venue.vendor_id)
    return bool(vp and vp.status == "approved")


def show_is_public(db: Session, show: Show) -> bool:
    return show.status == "active" and show.approval_status == "approved" and venue_is_public(db, show.screen.venue)


def commission_for(db: Session, vendor: VendorProfile) -> float:
    if vendor.commission_pct is not None:
        return float(vendor.commission_pct)
    return float(get_settings(db)["commission_pct"])
