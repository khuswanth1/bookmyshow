from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Timestamps

movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)
movie_languages = Table(
    "movie_languages",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("language_id", ForeignKey("languages.id", ondelete="CASCADE"), primary_key=True),
)
video_genres = Table(
    "video_genres",
    Base.metadata,
    Column("video_id", ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100), default="India", server_default="India")
    region: Mapped[str] = mapped_column(String(20), default="india", server_default="india")  # india | international
    lat: Mapped[float | None] = mapped_column(Float)  # internal: only used by "detect my location"
    lng: Mapped[float | None] = mapped_column(Float)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)


class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Movie(Base, Timestamps):
    __tablename__ = "movies"
    __table_args__ = (Index("ix_movies_release", "is_active", "release_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True)
    synopsis: Mapped[str] = mapped_column(Text, default="")
    duration_min: Mapped[int] = mapped_column(Integer, default=120)
    certificate: Mapped[str] = mapped_column(String(10), default="UA")
    release_date: Mapped[date] = mapped_column(Date)
    poster_url: Mapped[str | None] = mapped_column(String(500))
    backdrop_url: Mapped[str | None] = mapped_column(String(500))
    color_a: Mapped[str] = mapped_column(String(9), default="#1f2937")
    color_b: Mapped[str] = mapped_column(String(9), default="#e11d48")
    trailer_youtube_id: Mapped[str | None] = mapped_column(String(20))
    cast_members: Mapped[list] = mapped_column(JSONB, default=list)
    crew: Mapped[list] = mapped_column(JSONB, default=list)
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 1), default=0, server_default="0")
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    genres: Mapped[list[Genre]] = relationship(secondary=movie_genres, lazy="selectin")
    languages: Mapped[list[Language]] = relationship(secondary=movie_languages, lazy="selectin")


class MovieRating(Base):
    __tablename__ = "movie_ratings"
    __table_args__ = (UniqueConstraint("user_id", "movie_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)  # 1..10
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Venue(Base, Timestamps):
    __tablename__ = "venues"
    __table_args__ = (Index("ix_venues_city_type", "city_id", "type", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20), default="cinema")  # cinema | venue
    chain: Mapped[str | None] = mapped_column(String(100))  # PVR, INOX, regional chain...
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    amenities: Mapped[list] = mapped_column(JSONB, default=list)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor_profiles.id", ondelete="SET NULL"), index=True)
    # draft/pending/approved/rejected/suspended. Only `approved` theaters of approved vendors are public.
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    city: Mapped[City] = relationship(lazy="joined")
    screens: Mapped[list["Screen"]] = relationship(back_populates="venue", cascade="all, delete-orphan")


class Screen(Base):
    __tablename__ = "screens"
    __table_args__ = (UniqueConstraint("venue_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")  # active|maintenance
    # {"rows":[{"label":"A","category":"Silver","seats":12,"aisles":[4,8]}]}
    layout: Mapped[dict] = mapped_column(JSONB, default=dict)

    venue: Mapped[Venue] = relationship(back_populates="screens")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("screen_id", "row_label", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("screens.id", ondelete="CASCADE"), index=True)
    row_label: Mapped[str] = mapped_column(String(3))
    number: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30))
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # maintenance / broken seat
    block_reason: Mapped[str | None] = mapped_column(String(200))


class Show(Base, Timestamps):
    __tablename__ = "shows"
    __table_args__ = (
        UniqueConstraint("screen_id", "starts_at"),
        Index("ix_shows_movie_start", "movie_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("screens.id", ondelete="CASCADE"), index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"))
    format: Mapped[str] = mapped_column(String(20), default="2D")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prices: Mapped[dict] = mapped_column(JSONB, default=dict)  # category -> paise
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved", index=True)

    screen: Mapped[Screen] = relationship(lazy="joined")
    movie: Mapped[Movie] = relationship(lazy="joined")
    language: Mapped[Language] = relationship(lazy="joined")


class ShowSeat(Base):
    """One row per seat per show. status transitions: available -> locked -> booked (and back)."""

    __tablename__ = "show_seats"
    __table_args__ = (
        UniqueConstraint("show_id", "seat_id"),
        Index("ix_show_seats_show_status", "show_id", "status"),
        Index(
            "ix_show_seats_lock_expiry",
            "locked_until",
            postgresql_where=text("status = 'locked'"),
        ),
        Index("ix_show_seats_booking", "booking_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"))
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(30))
    price_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="available", server_default="available")
    locked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))

    seat: Mapped[Seat] = relationship(lazy="select")


class Video(Base, Timestamps):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    video_url: Mapped[str] = mapped_column(String(600))
    thumbnail_url: Mapped[str | None] = mapped_column(String(600))
    color_a: Mapped[str] = mapped_column(String(9), default="#0f172a")
    color_b: Mapped[str] = mapped_column(String(9), default="#6366f1")
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    year: Mapped[int | None] = mapped_column(Integer)
    license: Mapped[str] = mapped_column(String(100), default="")
    attribution: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str | None] = mapped_column(String(600))
    language_id: Mapped[int | None] = mapped_column(ForeignKey("languages.id"))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    genres: Mapped[list[Genre]] = relationship(secondary=video_genres, lazy="selectin")
    language: Mapped[Language | None] = relationship(lazy="joined")


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "video_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Faq(Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), default="General")
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Initiative(Base):
    """Configurable social initiative; users can add a small donation at checkout."""

    __tablename__ = "initiatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    partner_name: Mapped[str] = mapped_column(String(200), default="")
    amount_paise: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
