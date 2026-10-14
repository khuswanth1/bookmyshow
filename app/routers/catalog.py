import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import Date, cast, func, or_, select

from app.core.deps import CurrentUser, DB, OptionalUser, PageParams, paginate
from app.core.errors import AppError, not_found
from app.models import (
    City, Event, EventCategory, Faq, Genre, Initiative, Language, Movie, MovieRating, Screen, Show, ShowSeat, User,
    Venue, Video,
)
from app.schemas import (
    CategoryOut, CityOut, DetectCityOut, EventOut, FaqOut, GenreOut, InitiativeOut, LanguageOut, MovieOut, Paged,
    RatingIn, RatingOut, SearchOut, ShowtimeOut, VenueOut, VenueShowsOut, VideoOut,
)
from app.services.platform import public_show_conditions, public_venue_conditions, venue_is_public
from app.services.seats import utcnow

router = APIRouter(tags=["Catalog"])


# ------------------------------------------------------------------ reference data
@router.get("/cities", response_model=list[CityOut], summary="Active cities (India + international regions)")
def cities(db: DB, region: Literal["india", "international"] | None = None):
    q = select(City).where(City.is_active).order_by(City.is_popular.desc(), City.name)
    if region:
        q = q.where(City.region == region)
    return db.scalars(q).all()


def _haversine(lat1, lng1, lat2, lng2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


@router.get("/cities/detect", response_model=DetectCityOut, summary="Nearest active city to browser coordinates")
def detect_city(db: DB, lat: Annotated[float, Query(ge=-90, le=90)], lng: Annotated[float, Query(ge=-180, le=180)]):
    cs = db.scalars(select(City).where(City.is_active, City.lat.is_not(None), City.lng.is_not(None))).all()
    if not cs:
        raise not_found("City")
    best = min(cs, key=lambda c: _haversine(lat, lng, c.lat, c.lng))
    return DetectCityOut(city=CityOut.model_validate(best), distance_km=round(_haversine(lat, lng, best.lat, best.lng), 1))


@router.get("/genres", response_model=list[GenreOut])
def genres(db: DB):
    return db.scalars(select(Genre).order_by(Genre.name)).all()


@router.get("/languages", response_model=list[LanguageOut])
def languages(db: DB):
    return db.scalars(select(Language).where(Language.is_active).order_by(Language.name)).all()


@router.get("/categories", response_model=list[CategoryOut], summary="Event sub-categories per section")
def categories(db: DB, section: Literal["events", "plays", "sports", "activities"] | None = None):
    q = select(EventCategory).where(EventCategory.is_active).order_by(EventCategory.name)
    if section:
        q = q.where(EventCategory.section == section)
    return db.scalars(q).all()


@router.get("/faqs", response_model=list[FaqOut])
def faqs(db: DB):
    return db.scalars(select(Faq).where(Faq.is_active).order_by(Faq.category, Faq.sort_order)).all()


@router.get("/initiatives", response_model=list[InitiativeOut], summary="Active social initiatives (donate at checkout)")
def initiatives(db: DB):
    return db.scalars(select(Initiative).where(Initiative.is_active)).all()


# ------------------------------------------------------------------ movies
@router.get("/movies", response_model=Paged[MovieOut], summary="Search & filter movies")
def list_movies(
    db: DB, page: PageParams,
    q: str | None = Query(None, max_length=100),
    status: Literal["now_showing", "coming_soon", "all"] = "all",
    city_id: int | None = Query(None, description="Only movies with upcoming shows in this city (now_showing)"),
    genre_id: list[int] | None = Query(None),
    language_id: list[int] | None = Query(None),
    min_rating: float | None = Query(None, ge=0, le=10),
    certificate: str | None = None,
    sort: Literal["popular", "rating", "release", "title"] = "popular",
):
    today = date.today()
    now = utcnow()
    stmt = select(Movie).where(Movie.is_active)
    if q:
        stmt = stmt.where(Movie.title.ilike(f"%{q.strip()}%"))
    if status == "coming_soon":
        stmt = stmt.where(Movie.release_date > today)
    elif status == "now_showing":
        stmt = stmt.where(Movie.release_date <= today)
        show_exists = select(Show.id).join(Screen, Screen.id == Show.screen_id).join(Venue, Venue.id == Screen.venue_id).where(
            Show.movie_id == Movie.id, Show.starts_at > now, *public_show_conditions()
        )
        if city_id:
            show_exists = show_exists.where(Venue.city_id == city_id)
        # A released movie that has never been scheduled anywhere (just added by an admin) is listed too,
        # so it is visible straight away; once it has shows it follows the per-city rule above.
        never_scheduled = ~select(Show.id).where(Show.movie_id == Movie.id).exists()
        stmt = stmt.where(or_(show_exists.exists(), never_scheduled))
    if genre_id:
        stmt = stmt.where(Movie.genres.any(Genre.id.in_(genre_id)))
    if language_id:
        stmt = stmt.where(Movie.languages.any(Language.id.in_(language_id)))
    if min_rating is not None:
        stmt = stmt.where(Movie.rating_avg >= min_rating)
    if certificate:
        stmt = stmt.where(Movie.certificate == certificate)
    order = {
        "popular": (Movie.rating_count.desc(), Movie.rating_avg.desc()),
        "rating": (Movie.rating_avg.desc(),),
        "release": (Movie.release_date.desc(),),
        "title": (Movie.title,),
    }[sort]
    return paginate(db, stmt.order_by(*order, Movie.id), page)


@router.get("/movies/{movie_id}", response_model=MovieOut)
def get_movie(movie_id: int, db: DB):
    m = db.get(Movie, movie_id)
    if not m or not m.is_active:
        raise not_found("Movie")
    return m


@router.get("/movies/{movie_id}/shows", response_model=list[VenueShowsOut],
            summary="Showtimes for a movie in a city on a date, grouped by cinema")
def movie_shows(
    movie_id: int, db: DB, city_id: int, on: date | None = None,
    language_id: int | None = None, format: str | None = None,
    max_price_paise: int | None = Query(None, ge=0), tz_offset_minutes: int = Query(330, ge=-720, le=840),
):
    now = utcnow()
    day = on or (now + timedelta(minutes=tz_offset_minutes)).date()
    start = datetime.combine(day, time.min, tzinfo=timezone.utc) - timedelta(minutes=tz_offset_minutes)
    end = start + timedelta(days=1)
    stmt = (
        select(Show, Screen, Venue)
        .join(Screen, Screen.id == Show.screen_id)
        .join(Venue, Venue.id == Screen.venue_id)
        .where(Show.movie_id == movie_id, Venue.city_id == city_id, *public_show_conditions(),
               Show.starts_at >= max(start, now), Show.starts_at < end)
        .order_by(Venue.name, Show.starts_at)
    )
    if language_id:
        stmt = stmt.where(Show.language_id == language_id)
    if format:
        stmt = stmt.where(Show.format == format)
    rows = db.execute(stmt).unique().all()
    if not rows:
        return []
    ids = [s.id for s, _, _ in rows]
    avail = dict(db.execute(
        select(ShowSeat.show_id, func.count()).where(
            ShowSeat.show_id.in_(ids),
            or_(ShowSeat.status == "available", (ShowSeat.status == "locked") & (ShowSeat.locked_until < now)),
        ).group_by(ShowSeat.show_id)
    ).all())
    totals = dict(db.execute(select(ShowSeat.show_id, func.count()).where(ShowSeat.show_id.in_(ids)).group_by(ShowSeat.show_id)).all())
    grouped: dict[int, VenueShowsOut] = {}
    for s, scr, v in rows:
        if max_price_paise is not None and min(s.prices.values(), default=0) > max_price_paise:
            continue
        g = grouped.setdefault(v.id, VenueShowsOut(venue=VenueOut.model_validate(v), shows=[]))
        g.shows.append(ShowtimeOut(
            id=s.id, starts_at=s.starts_at, format=s.format, language=s.language.name, screen=scr.name,
            prices=s.prices, available=avail.get(s.id, 0), total=totals.get(s.id, 0),
        ))
    return list(grouped.values())


@router.get("/movies/{movie_id}/dates", response_model=list[date], summary="Dates that have upcoming shows in a city")
def movie_dates(movie_id: int, city_id: int, db: DB, tz_offset_minutes: int = Query(330, ge=-720, le=840)):
    local_day = cast(func.timezone("UTC", Show.starts_at) + timedelta(minutes=tz_offset_minutes), Date)
    rows = db.scalars(
        select(local_day)
        .join(Screen, Screen.id == Show.screen_id).join(Venue, Venue.id == Screen.venue_id)
        .where(Show.movie_id == movie_id, Venue.city_id == city_id, Show.starts_at > utcnow(), *public_show_conditions())
        .distinct().order_by(local_day)
    ).all()
    return rows


@router.get("/movies/{movie_id}/ratings", response_model=Paged[RatingOut])
def movie_ratings(movie_id: int, db: DB, page: PageParams):
    q = select(MovieRating).where(MovieRating.movie_id == movie_id).order_by(MovieRating.created_at.desc())
    res = paginate(db, q, page)
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_([r.user_id for r in res["items"]]))).all())
    res["items"] = [RatingOut(id=r.id, score=r.score, comment=r.comment, created_at=r.created_at,
                              user_name=names.get(r.user_id)) for r in res["items"]]
    return res


@router.put("/movies/{movie_id}/ratings", response_model=RatingOut, summary="Rate / review a movie (1-10)")
def rate_movie(movie_id: int, body: RatingIn, user: CurrentUser, db: DB):
    movie = db.scalar(select(Movie).where(Movie.id == movie_id).with_for_update())
    if not movie:
        raise not_found("Movie")
    r = db.scalar(select(MovieRating).where(MovieRating.movie_id == movie_id, MovieRating.user_id == user.id))
    if r:
        r.score, r.comment = body.score, body.comment
    else:
        r = MovieRating(movie_id=movie_id, user_id=user.id, score=body.score, comment=body.comment)
        db.add(r)
    db.flush()
    avg, cnt = db.execute(select(func.avg(MovieRating.score), func.count()).where(MovieRating.movie_id == movie_id)).one()
    movie.rating_avg, movie.rating_count = round(float(avg), 1), cnt
    db.commit()
    return RatingOut(id=r.id, score=r.score, comment=r.comment, created_at=r.created_at, user_name=user.name)


# ------------------------------------------------------------------ venues / cinemas
@router.get("/venues", response_model=Paged[VenueOut], summary="Cinemas and venues")
def venues(db: DB, page: PageParams, city_id: int | None = None, type: Literal["cinema", "venue"] | None = None,
           q: str | None = None):
    stmt = select(Venue).where(Venue.is_active, *public_venue_conditions()).order_by(Venue.name)
    if city_id:
        stmt = stmt.where(Venue.city_id == city_id)
    if type:
        stmt = stmt.where(Venue.type == type)
    if q:
        stmt = stmt.where(Venue.name.ilike(f"%{q}%"))
    return paginate(db, stmt, page)


@router.get("/venues/{venue_id}", response_model=VenueOut)
def venue(venue_id: int, db: DB):
    v = db.get(Venue, venue_id)
    if not v or not venue_is_public(db, v):
        raise not_found("Venue")
    return v


# ------------------------------------------------------------------ stream (public listing)
@router.get("/search", response_model=SearchOut, summary="Global search across movies, events, stream and venues")
def search(db: DB, q: Annotated[str, Query(min_length=2, max_length=100)], city_id: int | None = None):
    like = f"%{q.strip()}%"
    movies = db.scalars(select(Movie).where(Movie.is_active, Movie.title.ilike(like)).limit(6)).all()
    ev = select(Event).where(Event.status == "approved", Event.starts_at > utcnow(),
                             or_(Event.title.ilike(like), Event.venue_name.ilike(like)))
    if city_id:
        ev = ev.where(Event.city_id == city_id)
    events = db.scalars(ev.order_by(Event.starts_at).limit(6)).unique().all()
    videos = db.scalars(select(Video).where(Video.is_active, Video.title.ilike(like)).limit(6)).unique().all()
    vq = select(Venue).where(Venue.is_active, *public_venue_conditions(), Venue.name.ilike(like))
    if city_id:
        vq = vq.where(Venue.city_id == city_id)
    venues_ = db.scalars(vq.limit(6)).unique().all()
    return SearchOut(
        movies=[MovieOut.model_validate(m) for m in movies],
        events=[EventOut.model_validate(e) for e in events],
        videos=[VideoOut.model_validate(v) for v in videos],
        venues=[VenueOut.model_validate(v) for v in venues_],
    )
