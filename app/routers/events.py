from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import DB, PageParams, paginate
from app.core.errors import not_found
from app.models import Event, TicketType
from app.schemas import EventOut, Paged
from app.services.seats import utcnow

router = APIRouter(tags=["Events, Plays, Sports & Activities"])


@router.get("/events", response_model=Paged[EventOut], summary="List & filter events across all sections")
def list_events(
    db: DB, page: PageParams,
    section: Literal["events", "plays", "sports", "activities"] | None = None,
    category_id: list[int] | None = Query(None),
    city_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    min_price_paise: int | None = Query(None, ge=0),
    max_price_paise: int | None = Query(None, ge=0),
    language_id: list[int] | None = Query(None),
    featured: bool | None = None,
    exclusive: bool | None = None,
    available_only: bool = False,
    sort: Literal["date", "price_asc", "price_desc", "newest"] = "date",
):
    now = utcnow()
    stmt = select(Event).where(Event.status == "approved", func.coalesce(Event.ends_at, Event.starts_at) > now)
    if section:
        stmt = stmt.where(Event.section == section)
    if category_id:
        stmt = stmt.where(Event.category_id.in_(category_id))
    if city_id:
        stmt = stmt.where(Event.city_id == city_id)
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q.strip()}%") | Event.venue_name.ilike(f"%{q.strip()}%"))
    if date_from:
        stmt = stmt.where(Event.starts_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(Event.starts_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if language_id:
        stmt = stmt.where(Event.language_id.in_(language_id))
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if exclusive is not None:
        stmt = stmt.where(Event.is_exclusive == exclusive)
    if min_price_paise is not None or max_price_paise is not None:
        sub = select(TicketType.id).where(TicketType.event_id == Event.id)
        if min_price_paise is not None:
            sub = sub.where(TicketType.price_paise >= min_price_paise)
        if max_price_paise is not None:
            sub = sub.where(TicketType.price_paise <= max_price_paise)
        stmt = stmt.where(sub.exists())
    if available_only:
        stmt = stmt.where(
            select(TicketType.id).where(TicketType.event_id == Event.id, TicketType.total - TicketType.sold - TicketType.held > 0).exists()
        )
    min_price = select(func.min(TicketType.price_paise)).where(TicketType.event_id == Event.id).scalar_subquery()
    order = {
        "date": Event.starts_at, "price_asc": min_price, "price_desc": min_price.desc(), "newest": Event.id.desc(),
    }[sort]
    return paginate(db, stmt.order_by(order, Event.id), page)


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: DB):
    e = db.get(Event, event_id)
    if not e or e.status != "approved":
        raise not_found("Event")
    return e
