from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Timestamps
from .catalog import City, Language, Show, Venue
from .users import User


class EventCategory(Base):
    __tablename__ = "event_categories"
    __table_args__ = (UniqueConstraint("section", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    section: Mapped[str] = mapped_column(String(20), index=True)  # events | plays | sports | activities
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Event(Base, Timestamps):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_listing", "section", "city_id", "status", "starts_at"),
        Index("ix_events_organizer", "organizer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    section: Mapped[str] = mapped_column(String(20))
    category_id: Mapped[int] = mapped_column(ForeignKey("event_categories.id"))
    language_id: Mapped[int | None] = mapped_column(ForeignKey("languages.id"))
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id", ondelete="SET NULL"))
    venue_name: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    image_url: Mapped[str | None] = mapped_column(String(500))
    color_a: Mapped[str] = mapped_column(String(9), default="#111827")
    color_b: Mapped[str] = mapped_column(String(9), default="#7c3aed")
    age_limit: Mapped[str] = mapped_column(String(20), default="All ages")
    performers: Mapped[list] = mapped_column(JSONB, default=list)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_exclusive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    category: Mapped[EventCategory] = relationship(lazy="joined")
    city: Mapped[City] = relationship(lazy="joined")
    language: Mapped[Language | None] = relationship(lazy="joined")
    ticket_types: Mapped[list["TicketType"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin", order_by="TicketType.price_paise"
    )


class TicketType(Base):
    __tablename__ = "ticket_types"
    __table_args__ = (
        CheckConstraint("sold >= 0 AND held >= 0 AND sold + held <= total", name="ck_ticket_inventory"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300), default="")
    price_paise: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    sold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    held: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_per_booking: Mapped[int] = mapped_column(Integer, default=10, server_default="10")

    event: Mapped[Event] = relationship(back_populates="ticket_types")


class Coupon(Base, Timestamps):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="general")  # general | bank | corporate
    bank_name: Mapped[str | None] = mapped_column(String(100))
    discount_type: Mapped[str] = mapped_column(String(10), default="percent")  # percent | flat
    value: Mapped[int] = mapped_column(Integer)  # percent (1-100) or paise
    max_discount_paise: Mapped[int | None] = mapped_column(Integer)
    min_order_paise: Mapped[int] = mapped_column(Integer, default=0)
    applies_to: Mapped[str] = mapped_column(String(10), default="all")  # all | movie | event
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class GiftCard(Base, Timestamps):
    __tablename__ = "gift_cards"
    __table_args__ = (CheckConstraint("balance_paise >= 0", name="ck_gift_balance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(24), unique=True)  # assigned when payment succeeds
    initial_paise: Mapped[int] = mapped_column(Integer)
    balance_paise: Mapped[int] = mapped_column(Integer)
    purchaser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_name: Mapped[str] = mapped_column(String(120))
    recipient_email: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Booking(Base, Timestamps):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        Index("ix_bookings_user_created", "user_id", "created_at"),
        Index("ix_bookings_status_expiry", "status", "expires_at"),
        Index("ix_bookings_event", "event_id", "status"),
        Index("ix_bookings_show", "show_id", "status"),
        CheckConstraint("kind in ('movie','event')", name="ck_booking_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(10))
    show_id: Mapped[int | None] = mapped_column(ForeignKey("shows.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|confirmed|cancelled|expired|failed
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0)
    donation_paise: Mapped[int] = mapped_column(Integer, default=0)
    gift_card_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)  # subtotal + fee + tax + donation - discount
    payable_paise: Mapped[int] = mapped_column(Integer)  # total - gift card
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupons.id"))
    gift_card_id: Mapped[int | None] = mapped_column(ForeignKey("gift_cards.id"))
    initiative_id: Mapped[int | None] = mapped_column(ForeignKey("initiatives.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    qr_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    calendar_status: Mapped[str | None] = mapped_column(String(10))  # synced | failed | NULL (not attempted)
    calendar_event_id: Mapped[str | None] = mapped_column(String(64))
    calendar_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_paise: Mapped[int] = mapped_column(Integer, default=0)
    # Marketplace accounting (movie bookings at vendor theaters), set when the booking is confirmed
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor_profiles.id"), index=True)
    commission_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0, server_default="0")
    commission_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    vendor_share_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")
    show: Mapped[Show | None] = relationship(lazy="selectin")
    event: Mapped[Event | None] = relationship(lazy="selectin")
    coupon: Mapped[Coupon | None] = relationship(lazy="selectin")
    items: Mapped[list["BookingItem"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", lazy="selectin"
    )


class BookingItem(Base):
    __tablename__ = "booking_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    show_seat_id: Mapped[int | None] = mapped_column(ForeignKey("show_seats.id", ondelete="SET NULL"))
    ticket_type_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_types.id", ondelete="SET NULL"))
    label: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_paise: Mapped[int] = mapped_column(Integer)

    booking: Mapped[Booking] = relationship(back_populates="items")


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (Index("ix_redemptions_coupon_user", "coupon_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base, Timestamps):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_booking", "booking_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(12), default="booking")  # booking | gift_card
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    gift_card_id: Mapped[int | None] = mapped_column(ForeignKey("gift_cards.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="razorpay")
    order_id: Mapped[str] = mapped_column(String(64), unique=True)
    payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    signature: Mapped[str | None] = mapped_column(String(128))
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="created")  # created|paid|failed|refunded
    method: Mapped[str | None] = mapped_column(String(30))
    refund_id: Mapped[str | None] = mapped_column(String(64))
    refund_paise: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[dict | None] = mapped_column(JSONB)

    booking: Mapped[Booking | None] = relationship(lazy="selectin")
