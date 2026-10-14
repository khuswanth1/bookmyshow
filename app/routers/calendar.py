"""Google Calendar connection: connect once, then every confirmed booking is added automatically."""
import threading
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DB
from app.core.errors import AppError, not_found
from app.models import Booking, CalendarConnection
from app.schemas import Msg
from app.services import gcal
from app.services.platform import audit

router = APIRouter(tags=["Google Calendar"])


def _back(result: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url.rstrip('/')}/account/profile?{urlencode({'calendar': result})}", status_code=302)


@router.get("/calendar/status", summary="Is Google Calendar connected for me?")
def status(user: CurrentUser, db: DB):
    conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == user.id))
    return {"available": gcal.enabled(), "connected": bool(conn and conn.status == "connected"),
            "needs_reconnect": bool(conn and conn.status == "revoked"), "redirect_uri": settings.google_redirect_uri}


@router.post("/calendar/connect", summary="Start the Google consent flow; returns the URL to open")
def connect(user: CurrentUser):
    return {"url": gcal.auth_url(user.id)}


@router.get("/calendar/callback", include_in_schema=False)
def callback(db: DB, state: str, code: str | None = None, error: str | None = Query(None)):
    """Google redirects the browser here. The signed `state` identifies the user (the browser sends no bearer token)."""
    try:
        uid = gcal.read_state(state)
    except AppError:
        return _back("expired")
    if error or not code:
        return _back("denied")
    try:
        token = gcal.exchange_code(code)
    except AppError as e:
        return _back("denied" if e.code == "scope_missing" else "error")
    enc = gcal.encrypt(token)
    conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == uid))
    if conn:
        conn.refresh_token_enc, conn.status = enc, "connected"
    else:
        db.add(CalendarConnection(user_id=uid, refresh_token_enc=enc))
    from app.models import User
    audit(db, db.get(User, uid), "calendar.connect", "user", uid)
    db.commit()
    threading.Thread(target=gcal.sync_upcoming_for_user, args=(uid,), daemon=True, name="gcal-backfill").start()
    return _back("connected")


@router.delete("/calendar", response_model=Msg, summary="Disconnect Google Calendar (events already created stay)")
def disconnect(user: CurrentUser, db: DB):
    conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == user.id))
    if conn:
        token = None
        try:
            token = gcal.decrypt(conn.refresh_token_enc)
        except gcal.Revoked:
            pass
        db.delete(conn)
        audit(db, user, "calendar.disconnect", "user", user.id)
        db.commit()
        if token:
            gcal.background(gcal.revoke, token)
    return Msg(message="Google Calendar disconnected")


@router.post("/bookings/{booking_id}/calendar", summary="Retry adding a confirmed booking to my Google Calendar")
def retry(booking_id: int, user: CurrentUser, db: DB):
    b = db.get(Booking, booking_id)
    if not b or b.user_id != user.id:
        raise not_found("Booking")
    if b.status != "confirmed":
        raise AppError(409, "not_confirmed", "Only confirmed bookings can be added to a calendar")
    conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == user.id))
    if not conn or conn.status != "connected":
        raise AppError(409, "calendar_not_connected", "Connect Google Calendar first")
    if b.calendar_status == "failed":
        b.calendar_status = None
        db.commit()
    return {"status": gcal.sync_booking(b.id, attempts=1)}
