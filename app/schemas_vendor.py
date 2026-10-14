"""Schemas for the theater-vendor portal and the platform-admin approval workflow."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import BookingOut, CityOut, ORM, ScreenLayout, ShowOut


class VendorRegisterIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    contact_phone: str = Field(pattern=r"^\+?[0-9]{8,15}$")
    gst_number: str | None = Field(None, max_length=20)
    pan_number: str | None = Field(None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$", description="e.g. ABCDE1234F")
    address: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=2000)


class VendorOut(ORM):
    id: int
    user_id: int
    business_name: str
    contact_phone: str
    gst_number: str | None
    pan_number: str | None
    address: str | None
    description: str | None
    status: str
    rejection_reason: str | None
    commission_pct: float | None
    created_at: datetime
    reviewed_at: datetime | None
    user_email: str | None = None
    user_name: str | None = None
    theaters: int = 0


class VendorReview(BaseModel):
    status: Literal["approved", "rejected", "suspended", "pending"]
    reason: str | None = Field(None, max_length=500)
    commission_pct: float | None = Field(None, ge=0, le=60, description="Override the platform commission for this vendor")


class TheaterIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    chain: str | None = Field(None, max_length=100)
    city_id: int
    address: str = Field(min_length=3, max_length=300)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    amenities: list[str] = []


class TheaterOut(ORM):
    id: int
    name: str
    chain: str | None
    city_id: int
    city: CityOut
    address: str
    lat: float | None
    lng: float | None
    amenities: list
    vendor_id: int | None
    approval_status: str
    rejection_reason: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    is_active: bool
    screens_count: int = 0
    vendor_name: str | None = None


class TheaterReview(BaseModel):
    status: Literal["approved", "rejected", "suspended", "pending"]
    reason: str | None = Field(None, max_length=500)


class VendorScreenIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    layout: ScreenLayout
    status: Literal["active", "maintenance"] = "active"


class VendorScreenOut(ORM):
    id: int
    venue_id: int
    name: str
    status: str
    layout: dict
    seats: int = 0
    blocked: int = 0
    upcoming_shows: int = 0


class SeatAdminOut(BaseModel):
    id: int
    row: str
    number: int
    category: str
    is_blocked: bool
    block_reason: str | None


class SeatBlockIn(BaseModel):
    seat_ids: list[int] = Field(min_length=1, max_length=500)
    blocked: bool = True
    reason: str | None = Field(None, max_length=200)


class ShowSeatBlockIn(BaseModel):
    show_seat_ids: list[int] = Field(min_length=1, max_length=500)
    blocked: bool = True


class ShowPricesIn(BaseModel):
    prices: dict[str, int] = Field(description="Seat category -> price in paise")


class VendorShowOut(ShowOut):
    approval_status: str = "approved"
    movie_title: str
    screen_name: str
    theater_id: int
    theater_name: str
    language_name: str
    total: int = 0
    booked: int = 0
    blocked: int = 0
    locked: int = 0
    revenue_paise: int = 0


class ShowReview(BaseModel):
    show_ids: list[int] = Field(min_length=1, max_length=500)
    status: Literal["approved", "rejected"]


class VendorBookingOut(BookingOut):
    customer_name: str = ""
    theater: str = ""
    commission_paise: int = 0
    vendor_share_paise: int = 0


class CancelIn(BaseModel):
    reason: str | None = Field(None, max_length=300)


class MovieRequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    synopsis: str = ""
    duration_min: int = Field(120, ge=1, le=600)
    certificate: str = "UA"
    release_date: date | None = None
    languages: str = Field("", max_length=200)
    notes: str | None = Field(None, max_length=2000)


class MovieRequestOut(ORM):
    id: int
    vendor_id: int
    title: str
    synopsis: str
    duration_min: int
    certificate: str
    release_date: date | None
    languages: str
    notes: str | None
    status: str
    admin_note: str | None
    movie_id: int | None
    created_at: datetime
    vendor_name: str | None = None


class MovieRequestReview(BaseModel):
    status: Literal["approved", "rejected"]
    admin_note: str | None = Field(None, max_length=500)
    movie_id: int | None = Field(None, description="Link an existing movie instead of creating a new one")


class PayoutRequestIn(BaseModel):
    amount_paise: int | None = Field(None, ge=1, description="Defaults to the full available balance")


class PayoutOut(ORM):
    id: int
    vendor_id: int
    amount_paise: int
    status: str
    reference: str | None
    note: str | None
    created_at: datetime
    processed_at: datetime | None
    vendor_name: str | None = None


class PayoutProcess(BaseModel):
    status: Literal["paid", "rejected"]
    reference: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=500)


class AuditOut(ORM):
    id: int
    actor_id: int | None
    actor_email: str | None
    actor_role: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    meta: dict | None
    ip: str | None
    created_at: datetime


class SettingsIn(BaseModel):
    commission_pct: float | None = Field(None, ge=0, le=60)
    require_show_approval: bool | None = None
    payout_hold_days: int | None = Field(None, ge=0, le=60)
    min_payout_paise: int | None = Field(None, ge=0)


class ManagerCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
    password: str = Field(min_length=8, max_length=72, description="Temporary password the manager changes after signing in")
    theater_ids: list[int] = Field(min_length=1, max_length=50)


class ManagerPatchIn(BaseModel):
    theater_ids: list[int] | None = Field(None, min_length=1, max_length=50)
    disabled: bool | None = None


class ManagerOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    status: str
    rejection_reason: str | None = None
    theater_ids: list[int]
    theater_names: list[str]
    vendor: str | None = None
    created_at: datetime


class StaffReviewIn(BaseModel):
    status: Literal["approved", "rejected"]
    reason: str | None = Field(None, max_length=500)
