import re
from typing import Literal

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.deps import CurrentUser, DB, OptionalUser, PageParams, paginate
from app.core.errors import AppError, not_found
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models import (
    Event, Favorite, Genre, Language, Movie, NewsletterSubscriber, Notification, SupportTicket, User, Video, WatchlistItem,
)
from app.schemas import (
    EventOut, Msg, MovieOut, NewsletterIn, NotificationOut, Paged, SupportIn, SupportOut, VideoOut,
)
from app.services.realtime import hub

router = APIRouter(tags=["User features, Stream & Support"])


# ------------------------------------------------------------------ stream
def _video_out(v: Video, watch_ids: set[int]) -> VideoOut:
    o = VideoOut.model_validate(v)
    o.in_watchlist = v.id in watch_ids
    return o


def _watch_ids(db, user) -> set[int]:
    if not user:
        return set()
    return set(db.scalars(select(WatchlistItem.video_id).where(WatchlistItem.user_id == user.id)))


@router.get("/videos", response_model=Paged[VideoOut], summary="Stream catalog (legally available demo content)")
def videos(
    db: DB, page: PageParams, user: OptionalUser,
    q: str | None = Query(None, max_length=100), genre_id: int | None = None, language_id: int | None = None,
    featured: bool | None = None, sort: Literal["newest", "title", "year"] = "newest",
):
    stmt = select(Video).where(Video.is_active)
    if q:
        stmt = stmt.where(or_(Video.title.ilike(f"%{q}%"), Video.description.ilike(f"%{q}%")))
    if genre_id:
        stmt = stmt.where(Video.genres.any(Genre.id == genre_id))
    if language_id:
        stmt = stmt.where(Video.language_id == language_id)
    if featured is not None:
        stmt = stmt.where(Video.is_featured == featured)
    order = {"newest": Video.id.desc(), "title": Video.title, "year": Video.year.desc()}[sort]
    res = paginate(db, stmt.order_by(order), page)
    ids = _watch_ids(db, user)
    res["items"] = [_video_out(v, ids) for v in res["items"]]
    return res


@router.get("/videos/watchlist", response_model=list[VideoOut], summary="My watchlist")
def watchlist(user: CurrentUser, db: DB):
    vids = db.scalars(
        select(Video).join(WatchlistItem, WatchlistItem.video_id == Video.id)
        .where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.id.desc())
    ).unique().all()
    return [_video_out(v, {v.id for v in vids}) for v in vids]


@router.get("/videos/{video_id}", response_model=VideoOut)
def video(video_id: int, db: DB, user: OptionalUser):
    v = db.get(Video, video_id)
    if not v or not v.is_active:
        raise not_found("Video")
    return _video_out(v, _watch_ids(db, user))


@router.put("/videos/{video_id}/watchlist", response_model=Msg)
def add_watch(video_id: int, user: CurrentUser, db: DB):
    if not db.get(Video, video_id):
        raise not_found("Video")
    db.execute(pg_insert(WatchlistItem).values(user_id=user.id, video_id=video_id).on_conflict_do_nothing())
    db.commit()
    return Msg(message="Added to watchlist")


@router.delete("/videos/{video_id}/watchlist", response_model=Msg)
def remove_watch(video_id: int, user: CurrentUser, db: DB):
    db.execute(delete(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.video_id == video_id))
    db.commit()
    return Msg(message="Removed from watchlist")


# ------------------------------------------------------------------ favorites
@router.get("/favorites", summary="My favorite movies and events")
def favorites(user: CurrentUser, db: DB):
    favs = db.scalars(select(Favorite).where(Favorite.user_id == user.id).order_by(Favorite.id.desc())).all()
    mids = [f.entity_id for f in favs if f.entity_type == "movie"]
    eids = [f.entity_id for f in favs if f.entity_type == "event"]
    movies = db.scalars(select(Movie).where(Movie.id.in_(mids))).all() if mids else []
    events = db.scalars(select(Event).where(Event.id.in_(eids))).unique().all() if eids else []
    return {
        "movies": [MovieOut.model_validate(m) for m in movies],
        "events": [EventOut.model_validate(e) for e in events],
        "keys": [f"{f.entity_type}:{f.entity_id}" for f in favs],
    }


@router.put("/favorites/{entity_type}/{entity_id}", response_model=Msg)
def add_favorite(entity_type: Literal["movie", "event"], entity_id: int, user: CurrentUser, db: DB):
    model = Movie if entity_type == "movie" else Event
    if not db.get(model, entity_id):
        raise not_found(entity_type.title())
    db.execute(pg_insert(Favorite).values(user_id=user.id, entity_type=entity_type, entity_id=entity_id).on_conflict_do_nothing())
    db.commit()
    return Msg(message="Added to favorites")


@router.delete("/favorites/{entity_type}/{entity_id}", response_model=Msg)
def remove_favorite(entity_type: Literal["movie", "event"], entity_id: int, user: CurrentUser, db: DB):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.entity_type == entity_type,
                                      Favorite.entity_id == entity_id))
    db.commit()
    return Msg(message="Removed from favorites")


# ------------------------------------------------------------------ notifications
@router.get("/notifications", response_model=Paged[NotificationOut])
def notifications(user: CurrentUser, db: DB, page: PageParams):
    return paginate(db, select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()), page)


@router.get("/notifications/unread-count")
def unread(user: CurrentUser, db: DB):
    from sqlalchemy import func

    return {"count": db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))}


@router.post("/notifications/read-all", response_model=Msg)
def read_all(user: CurrentUser, db: DB):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
    return Msg(message="ok")


# ------------------------------------------------------------------ support
@router.post("/support/tickets", response_model=SupportOut, status_code=201, summary="Contact support")
def create_ticket(body: SupportIn, db: DB, user: OptionalUser):
    t = SupportTicket(user_id=user.id if user else None, email=str(body.email).lower(), subject=body.subject,
                      message=body.message, booking_code=body.booking_code.strip().upper() if body.booking_code else None,
                      category=body.category)
    db.add(t)
    db.commit()
    return t


@router.get("/support/tickets", response_model=list[SupportOut], summary="My support tickets")
def my_tickets(user: CurrentUser, db: DB):
    return db.scalars(select(SupportTicket).where(
        or_(SupportTicket.user_id == user.id, SupportTicket.email == user.email.lower())
    ).order_by(SupportTicket.id.desc())).all()


@router.post("/newsletter", response_model=Msg, status_code=201, summary="Subscribe to the newsletter")
def subscribe(body: NewsletterIn, db: DB):
    db.execute(pg_insert(NewsletterSubscriber).values(email=str(body.email).lower()).on_conflict_do_nothing())
    db.commit()
    return Msg(message="Thanks for subscribing!")


# ------------------------------------------------------------------ websocket (private)
@router.websocket("/ws/me")
async def ws_me(ws: WebSocket, token: str):
    """Private stream of booking/notification events for the signed-in user. Auth via ?token=<access jwt>."""
    try:
        uid = int(decode_token(token, "access")["sub"])
    except AppError:
        await ws.close(code=4401)
        return
    with SessionLocal() as db:  # a valid signature is not enough: the account must still exist and be active
        active = db.scalar(select(User.is_active).where(User.id == uid))
    if not active:
        await ws.close(code=4401)
        return
    room = f"user:{uid}"
    if not await hub.join(room, ws):
        return
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room, ws)
