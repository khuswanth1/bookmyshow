"""Pydantic request/response models (these drive the OpenAPI/Swagger docs)."""
import re
from datetime import date, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, create_model, field_validator, model_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paged(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class Msg(BaseModel):
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorOut(BaseModel):
    error: ErrorBody


def partial(model: type[BaseModel], name: str | None = None) -> type[BaseModel]:
    """Same fields as `model`, all optional (for PATCH bodies)."""
    fields = {k: (f.annotation | None, None) for k, f in model.model_fields.items()}
    return create_model(name or f"{model.__name__}Patch", **fields)  # type: ignore[call-overload]


# ---------------------------------------------------------------- auth / users
Password = Annotated[str, Field(min_length=8, max_length=72)]


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: Password
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{8,15}$")

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain letters and numbers")
        return v


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class GoogleIn(BaseModel):
    credential: str = Field(description="Google Identity Services ID token (JWT)")


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(ORM):
    id: int
    email: str
    name: str
    phone: str | None
    avatar_url: str | None
    role: str
    city_id: int | None
    is_active: bool
    email_verified: bool = False
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{8,15}$")
    city_id: int | None = None
    avatar_url: str | None = Field(None, max_length=500)


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: Password


class AdminUserUpdate(BaseModel):
    role: Literal["user", "organizer", "vendor", "admin", "checkin", "support", "manager"] | None = None
    is_active: bool | None = None
    name: str | None = None


# ---------------------------------------------------------------- catalog
class CityIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", max_length=100)
    state: str | None = None
    country: str = "India"
    region: Literal["india", "international"] = "india"
    is_popular: bool = False
    is_active: bool = True


class CityOut(CityIn, ORM):
    id: int


class GenreIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", max_length=60)


class GenreOut(GenreIn, ORM):
    id: int


class LanguageIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    code: str = Field(min_length=2, max_length=10)
    is_active: bool = True


class LanguageOut(LanguageIn, ORM):
    id: int


class CategoryIn(BaseModel):
    section: Literal["events", "plays", "sports", "activities"]
    name: str = Field(min_length=1, max_length=80)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", max_length=80)
    is_active: bool = True


class CategoryOut(CategoryIn, ORM):
    id: int


class MovieIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    synopsis: str = ""
    duration_min: int = Field(120, ge=1, le=600)
    certificate: str = "UA"
    release_date: date
    poster_url: str | None = None
    backdrop_url: str | None = None
    color_a: str = "#1f2937"
    color_b: str = "#e11d48"
    trailer_youtube_id: str | None = None
    rating_avg: float = Field(0, ge=0, le=10)
    cast_members: list[dict] = []
    crew: list[dict] = []
    is_active: bool = True
    genre_ids: list[int] = []
    language_ids: list[int] = []


class MovieOut(ORM):
    id: int
    title: str
    slug: str
    synopsis: str
    duration_min: int
    certificate: str
    release_date: date
    poster_url: str | None
    backdrop_url: str | None
    color_a: str
    color_b: str
    trailer_youtube_id: str | None
    cast_members: list[dict]
    crew: list[dict]
    rating_avg: float
    rating_count: int
    is_active: bool
    genres: list[GenreOut]
    languages: list[LanguageOut]


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=10)
    comment: str | None = Field(None, max_length=1000)


class RatingOut(ORM):
    id: int
    score: int
    comment: str | None
    created_at: datetime
    user_name: str | None = None


class VenueIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["cinema", "venue"] = "cinema"
    chain: str | None = None
    city_id: int
    address: str = Field(min_length=1, max_length=300)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    amenities: list[str] = []
    is_active: bool = True


class VenueOut(VenueIn, ORM):
    id: int
    organizer_id: int | None = None
    city: CityOut


class SeatRowIn(BaseModel):
    label: str = Field(min_length=1, max_length=3)
    category: str = Field(min_length=1, max_length=30)
    seats: int = Field(ge=1, le=40)
    aisles: list[int] = []


class ScreenLayout(BaseModel):
    rows: list[SeatRowIn] = Field(min_length=1, max_length=40)


class ScreenIn(BaseModel):
    venue_id: int
    name: str = Field(min_length=1, max_length=60)
    layout: ScreenLayout


class ScreenOut(ORM):
    id: int
    venue_id: int
    name: str
    layout: dict


class ShowOut(ORM):
    id: int
    screen_id: int
    movie_id: int
    language_id: int
    format: str
    starts_at: datetime
    ends_at: datetime
    prices: dict
    status: str


class ShowBulkIn(BaseModel):
    movie_id: int
    screen_id: int
    language_id: int
    format: str = "2D"
    dates: list[date] = Field(min_length=1, max_length=31)
    times: list[str] = Field(min_length=1, description="Local HH:MM times, e.g. ['10:00','14:00']")
    prices: dict[str, int] = Field(description="Seat category -> price in paise")
    utc_offset_minutes: int = 330

    @field_validator("times")
    @classmethod
    def _times(cls, v: list[str]) -> list[str]:
        for t in v:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
                raise ValueError(f"Invalid time {t}")
        return v


class ShowtimeOut(BaseModel):
    id: int
    starts_at: datetime
    format: str
    language: str
    screen: str
    prices: dict
    available: int
    total: int


class VenueShowsOut(BaseModel):
    venue: VenueOut
    shows: list[ShowtimeOut]


class SeatOut(BaseModel):
    id: int
    row: str
    number: int
    category: str
    price_paise: int
    status: Literal["available", "locked", "booked", "blocked"]
    mine: bool


class ShowDetailOut(BaseModel):
    id: int
    starts_at: datetime
    ends_at: datetime
    format: str
    language: str
    movie: MovieOut
    venue: VenueOut
    screen_name: str
    prices: dict
    layout: dict
    seats: list[SeatOut]
    max_seats: int
    lock_minutes: int


class LockIn(BaseModel):
    seat_ids: list[int] = Field(max_length=20)


class LockOut(BaseModel):
    seat_ids: list[int]
    expires_at: datetime | None


# ---------------------------------------------------------------- events
class TicketTypeIn(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    price_paise: int = Field(ge=0, le=100_000_00)
    total: int = Field(ge=1, le=1_000_000)
    max_per_booking: int = Field(10, ge=1, le=20)


class TicketTypeOut(ORM):
    id: int
    name: str
    description: str
    price_paise: int
    total: int
    sold: int
    held: int
    max_per_booking: int
    available: int = 0

    @model_validator(mode="after")
    def _avail(self):
        self.available = max(0, self.total - self.sold - self.held)
        return self


class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    section: Literal["events", "plays", "sports", "activities"]
    category_id: int
    language_id: int | None = None
    city_id: int
    venue_id: int | None = None
    venue_name: str = ""
    address: str = ""
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    starts_at: datetime
    ends_at: datetime | None = None
    image_url: str | None = None
    color_a: str = "#111827"
    color_b: str = "#7c3aed"
    age_limit: str = "All ages"
    performers: list[str] = []
    ticket_types: list[TicketTypeIn] = Field(min_length=1, max_length=10)


class EventOut(ORM):
    id: int
    title: str
    slug: str
    description: str
    section: str
    category: CategoryOut
    language: LanguageOut | None
    city: CityOut
    venue_id: int | None
    venue_name: str
    address: str
    lat: float | None
    lng: float | None
    starts_at: datetime
    ends_at: datetime | None
    image_url: str | None
    color_a: str
    color_b: str
    age_limit: str
    performers: list
    is_featured: bool
    is_exclusive: bool
    status: str
    organizer_id: int | None
    ticket_types: list[TicketTypeOut]
    min_price_paise: int = 0
    sold_out: bool = False

    @model_validator(mode="after")
    def _derived(self):
        tt = self.ticket_types
        self.min_price_paise = min((t.price_paise for t in tt), default=0)
        self.sold_out = bool(tt) and all(t.available <= 0 for t in tt)
        return self


class EventAdminPatch(BaseModel):
    status: Literal["draft", "pending", "approved", "rejected", "cancelled"] | None = None
    is_featured: bool | None = None
    is_exclusive: bool | None = None


# ---------------------------------------------------------------- booking & payments
class TicketSel(BaseModel):
    ticket_type_id: int
    quantity: int = Field(ge=1, le=20)


class BookingCreate(BaseModel):
    kind: Literal["movie", "event"]
    idempotency_key: str = Field(min_length=8, max_length=64, description="Client-generated UUID; retries are safe")
    show_id: int | None = None
    seat_ids: list[int] | None = Field(None, max_length=20)
    event_id: int | None = None
    tickets: list[TicketSel] | None = Field(None, max_length=10)
    coupon_code: str | None = Field(None, max_length=40)
    gift_card_code: str | None = Field(None, max_length=24)
    initiative_id: int | None = None


class BookingItemOut(ORM):
    id: int
    label: str
    quantity: int
    unit_price_paise: int


class BookingOut(ORM):
    id: int
    code: str
    kind: str
    status: str
    show_id: int | None
    event_id: int | None
    subtotal_paise: int
    fee_paise: int
    tax_paise: int
    discount_paise: int
    donation_paise: int
    gift_card_paise: int
    total_paise: int
    payable_paise: int
    qr_token: str | None
    expires_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    refund_paise: int
    created_at: datetime
    items: list[BookingItemOut]
    title: str = ""
    subtitle: str = ""
    starts_at: datetime | None = None
    venue: str = ""
    poster: dict = {}
    can_cancel: bool = False
    calendar_url: str | None = None
    calendar_status: str | None = None


class RazorpayCheckout(BaseModel):
    key_id: str
    order_id: str
    amount: int
    currency: str = "INR"


class CheckoutOut(BaseModel):
    booking: BookingOut
    razorpay: RazorpayCheckout | None = Field(None, description="null when nothing is left to pay")


class VerifyPaymentIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentOut(ORM):
    id: int
    purpose: str
    booking_id: int | None
    order_id: str
    payment_id: str | None
    amount_paise: int
    currency: str
    status: str
    method: str | None
    refund_paise: int
    created_at: datetime
    booking_code: str | None = None


class VerifyOut(BaseModel):
    status: Literal["paid"]
    booking: BookingOut | None = None
    gift_card_code: str | None = None


# ---------------------------------------------------------------- commerce
class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: Literal["general", "bank", "corporate"] = "general"
    bank_name: str | None = None
    discount_type: Literal["percent", "flat"] = "percent"
    value: int = Field(ge=1)
    max_discount_paise: int | None = Field(None, ge=0)
    min_order_paise: int = Field(0, ge=0)
    applies_to: Literal["all", "movie", "event"] = "all"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = Field(None, ge=1)
    per_user_limit: int = Field(1, ge=1)
    is_public: bool = True
    is_active: bool = True


class CouponOut(CouponIn, ORM):
    id: int
    used_count: int


class CouponValidateIn(BaseModel):
    code: str
    kind: Literal["movie", "event"]
    subtotal_paise: int = Field(ge=0)


class CouponValidateOut(BaseModel):
    code: str
    title: str
    discount_paise: int


class GiftCardCreate(BaseModel):
    amount_paise: int = Field(ge=500_00, le=10_000_00, description="₹500 – ₹10,000")
    recipient_name: str = Field(min_length=2, max_length=120)
    recipient_email: EmailStr
    message: str | None = Field(None, max_length=500)


class GiftCardOut(ORM):
    id: int
    code: str | None
    initial_paise: int
    balance_paise: int
    recipient_name: str
    recipient_email: str
    message: str | None
    status: str
    expires_at: datetime | None
    created_at: datetime


class GiftCardCheckout(BaseModel):
    gift_card: GiftCardOut
    razorpay: RazorpayCheckout


class GiftCardBalance(BaseModel):
    code: str
    balance_paise: int
    status: str
    expires_at: datetime | None


class InitiativeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    partner_name: str = ""
    amount_paise: int = Field(1000, ge=100, le=100_000)
    is_active: bool = True


class InitiativeOut(InitiativeIn, ORM):
    id: int


# ---------------------------------------------------------------- stream & content
class VideoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    video_url: str = Field(max_length=600, pattern=r"^https?://")
    thumbnail_url: str | None = None
    color_a: str = "#0f172a"
    color_b: str = "#6366f1"
    duration_sec: int = Field(0, ge=0)
    year: int | None = None
    license: str = ""
    attribution: str = ""
    source_url: str | None = None
    language_id: int | None = None
    is_featured: bool = False
    is_active: bool = True
    genre_ids: list[int] = []


class VideoOut(ORM):
    id: int
    title: str
    slug: str
    description: str
    video_url: str
    thumbnail_url: str | None
    color_a: str
    color_b: str
    duration_sec: int
    year: int | None
    license: str
    attribution: str
    source_url: str | None
    language: LanguageOut | None
    genres: list[GenreOut]
    is_featured: bool
    is_active: bool
    in_watchlist: bool = False


class FaqIn(BaseModel):
    category: str = "General"
    question: str = Field(min_length=3, max_length=300)
    answer: str = Field(min_length=3)
    sort_order: int = 0
    is_active: bool = True


class FaqOut(FaqIn, ORM):
    id: int


class SupportIn(BaseModel):
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=4000)
    booking_code: str | None = Field(None, max_length=20)
    category: Literal["booking", "payment", "refund", "account", "other"] = "other"


class SupportOut(ORM):
    id: int
    email: str
    subject: str
    message: str
    booking_code: str | None
    status: str
    priority: str = "normal"
    category: str = "other"
    admin_reply: str | None
    created_at: datetime


class SupportAdminPatch(BaseModel):
    status: Literal["open", "in_progress", "waiting_customer", "escalated", "resolved"] | None = None
    admin_reply: str | None = None


class NewsletterIn(BaseModel):
    email: EmailStr


class NotificationOut(ORM):
    id: int
    title: str
    body: str
    kind: str
    is_read: bool
    created_at: datetime


class OrganizerRegisterIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_phone: str = Field(pattern=r"^\+?[0-9]{8,15}$")
    website: str | None = Field(None, max_length=300)
    gst_number: str | None = Field(None, max_length=20)
    description: str | None = Field(None, max_length=2000)


class OrganizerOut(ORM):
    id: int
    user_id: int
    company_name: str
    contact_phone: str
    website: str | None
    gst_number: str | None
    description: str | None
    status: str
    created_at: datetime
    user_email: str | None = None
    user_name: str | None = None


class OrganizerReview(BaseModel):
    status: Literal["approved", "rejected", "pending"]


class SearchOut(BaseModel):
    movies: list[MovieOut]
    events: list[EventOut]
    videos: list[VideoOut]
    venues: list[VenueOut]


class DetectCityOut(BaseModel):
    city: CityOut
    distance_km: float


# ---------------------------------------------------------------- OTP / password reset
class OtpSentOut(BaseModel):
    message: str
    dev_code: str | None = Field(None, description="Only present in non-production environments without SMTP")


Code6 = Annotated[str, Field(pattern=r"^\d{6}$", description="6-digit one-time code")]


class EmailVerifyIn(BaseModel):
    code: Code6


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    email: EmailStr
    code: Code6
    new_password: Password


# ---------------------------------------------------------------- staff accounts, check-in, helpdesk
class StaffCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: Password
    role: Literal["checkin", "support"]


class StaffAssignIn(BaseModel):
    email: EmailStr


class StaffOut(ORM):
    id: int
    name: str
    email: str


class ScanIn(BaseModel):
    event_id: int
    qr: str | None = Field(None, max_length=200, description="Scanned QR payload: BMS|<code>|<token>")
    booking_code: str | None = Field(None, max_length=20, description="Manual fallback when the QR cannot be read")

    @model_validator(mode="after")
    def _one(self):
        if not (self.qr or self.booking_code):
            raise ValueError("Provide a scanned QR payload or a booking code")
        return self


class ScanOut(BaseModel):
    result: Literal["admitted", "duplicate", "invalid", "wrong_event", "not_confirmed"]
    message: str
    booking_code: str | None = None
    holder_name: str | None = None
    tickets: int = 0
    items: list[str] = []
    checked_in_at: datetime | None = None


class HelpdeskReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    internal: bool = False


class HelpdeskPatch(BaseModel):
    status: Literal["open", "in_progress", "waiting_customer", "resolved"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assign: Literal["me", "none"] | None = None


class EscalateIn(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class CustomerReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class SupportMessageOut(ORM):
    id: int
    author_role: str
    author_name: str | None = None
    body: str
    is_internal: bool
    created_at: datetime
