from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.deps import CurrentUser, DB, OptionalUser
from app.core.errors import not_found
from app.models import Show
from app.schemas import LockIn, LockOut, MovieOut, SeatOut, ShowDetailOut, VenueOut
from app.services import seats as seat_svc
from app.services.booking import commit
from app.services.platform import show_is_public
from app.services.realtime import hub, publish_seats

router = APIRouter(tags=["Shows & Seats"])


@router.get("/shows/{show_id}", response_model=ShowDetailOut, summary="Show details with the live seat map")
def show_detail(show_id: int, db: DB, user: OptionalUser):
    show = db.get(Show, show_id)
    if not show or not show_is_public(db, show):
        raise not_found("Show")
    venue = show.screen.venue
    return ShowDetailOut(
        id=show.id, starts_at=show.starts_at, ends_at=show.ends_at, format=show.format, language=show.language.name,
        movie=MovieOut.model_validate(show.movie), venue=VenueOut.model_validate(venue), screen_name=show.screen.name,
        prices=show.prices, layout=show.screen.layout,
        seats=[SeatOut(**s) for s in seat_svc.seat_map(db, show.id, user.id if user else None)],
        max_seats=settings.max_seats_per_booking, lock_minutes=settings.seat_lock_minutes,
    )


@router.put("/shows/{show_id}/locks", response_model=LockOut,
            summary="Hold exactly these seats for you (replaces your previous holds on this show)")
def put_locks(show_id: int, body: LockIn, user: CurrentUser, db: DB):
    show = db.get(Show, show_id)
    if not show:
        raise not_found("Show")
    expiry, changes = seat_svc.set_locks(db, user.id, show, body.seat_ids)
    commit(db)
    publish_seats(show_id, changes)
    return LockOut(seat_ids=body.seat_ids, expires_at=expiry)


@router.delete("/shows/{show_id}/locks", response_model=LockOut, summary="Release all your holds on this show")
def delete_locks(show_id: int, user: CurrentUser, db: DB):
    show = db.get(Show, show_id)
    if not show:
        raise not_found("Show")
    _, changes = seat_svc.set_locks(db, user.id, show, [])
    commit(db)
    publish_seats(show_id, changes)
    return LockOut(seat_ids=[], expires_at=None)


@router.websocket("/ws/shows/{show_id}")
async def ws_show(ws: WebSocket, show_id: int):
    """Public read-only stream of seat status changes: {"type":"seats","show_id":1,"seats":[{"id":5,"status":"locked"}]}"""
    room = f"show:{show_id}"
    if not await hub.join(room, ws):
        return
    try:
        await ws.send_json({"type": "hello", "viewers": hub.count(room)})
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room, ws)
