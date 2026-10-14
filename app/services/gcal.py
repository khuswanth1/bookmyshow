"""Google Calendar integration: OAuth (authorization-code, offline) and idempotent event sync for confirmed bookings.

Scope is `calendar.events` only. Refresh tokens are stored encrypted (Fernet key derived from JWT_SECRET).
"""
import base64
import hashlib
import logging
import threading
import time
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import Booking, CalendarConnection
from app.services.notify import notify
from app.services.seats import utcnow

log = logging.getLogger("gcal")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
TIMEOUT = 10


class Revoked(Exception):
    """The user revoked access (or the refresh token is no longer valid)."""


def enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


# ------------------------------------------------------------------ secrets at rest
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"gcal|{settings.jwt_secret}".encode()).digest()))


def encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt(blob: str) -> str:
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken as e:
        raise Revoked("stored token cannot be decrypted") from e


# ------------------------------------------------------------------ OAuth
def make_state(user_id: int) -> str:
    exp = utcnow() + timedelta(minutes=10)
    return jwt.encode({"sub": str(user_id), "typ": "cal_state", "exp": exp}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def read_state(state: str) -> int:
    try:
        d = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if d.get("typ") != "cal_state":
            raise ValueError
        return int(d["sub"])
    except Exception as e:
        raise AppError(400, "bad_state", "This connection link has expired. Please try connecting again.") from e


def auth_url(user_id: int) -> str:
    if not enabled():
        raise AppError(503, "calendar_unavailable", "Google Calendar is not configured on this server")
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": settings.google_redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": make_state(user_id),
    })


def exchange_code(code: str) -> str:
    """Authorization code -> refresh token."""
    r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code"})
    data = r.json() if r.content else {}
    if r.status_code != 200 or not data.get("refresh_token"):
        log.warning("calendar code exchange failed: %s %s", r.status_code, data.get("error"))
        raise AppError(502, "google_exchange_failed", "Google did not return calendar access. Please try again.")
    if SCOPE not in (data.get("scope") or "").split():
        raise AppError(400, "scope_missing", "Calendar permission was not granted.")
    return data["refresh_token"]


def _access_token(refresh_token: str) -> str:
    r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
        "refresh_token": refresh_token, "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret, "grant_type": "refresh_token"})
    data = r.json() if r.content else {}
    if r.status_code == 400 and data.get("error") == "invalid_grant":
        raise Revoked("refresh token rejected")
    r.raise_for_status()
    return data["access_token"]


def revoke(refresh_token: str) -> None:
    try:
        httpx.post("https://oauth2.googleapis.com/revoke", params={"token": refresh_token}, timeout=TIMEOUT)
    except httpx.HTTPError:
        log.warning("calendar token revoke call failed (the local connection is removed anyway)")


# ------------------------------------------------------------------ events
def event_id(booking_code: str) -> str:
    """Deterministic Google event id (base32hex charset), so a retry can never create a duplicate."""
    return "bms" + hashlib.sha1(booking_code.encode()).hexdigest()


def build_event(b: Booking) -> dict:
    if b.kind == "movie" and b.show:
        s = b.show
        v = s.screen.venue
        title, start, end = f"🎬 {s.movie.title}", s.starts_at, s.ends_at
        where = f"{v.name}, {v.address}, {v.city.name}"
        detail = f"{s.language.name} · {s.format} · {s.screen.name}"
    else:
        e = b.event
        title, start = f"🎟️ {e.title}", e.starts_at
        end = e.ends_at or e.starts_at + timedelta(hours=3)
        where = ", ".join(x for x in (e.venue_name, e.address) if x)
        detail = e.category.name
    seats = ", ".join(i.label for i in b.items)
    return {
        "id": event_id(b.code), "summary": title, "location": where,
        "description": f"{detail}\nBooking: {b.code}\nTickets: {seats}\nShow the QR code from your booking at the entrance:\n"
                       f"{settings.frontend_url}/bookings/{b.id}",
        "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 120}]},
    }


def insert_event(access_token: str, body: dict) -> None:
    r = httpx.post(EVENTS_URL, json=body, headers={"Authorization": f"Bearer {access_token}"}, timeout=TIMEOUT)
    if r.status_code == 409:  # same booking already on the calendar: this is success
        return
    if r.status_code in (401, 403) and "insufficient" not in r.text.lower() and "rate" not in r.text.lower():
        raise Revoked(f"calendar rejected token: {r.status_code}")
    r.raise_for_status()


def delete_event(access_token: str, gid: str) -> None:
    r = httpx.delete(f"{EVENTS_URL}/{gid}", headers={"Authorization": f"Bearer {access_token}"}, timeout=TIMEOUT)
    if r.status_code not in (200, 204, 404, 410):
        r.raise_for_status()


# ------------------------------------------------------------------ sync (runs outside the request)
def sync_booking(booking_id: int, attempts: int = 3) -> str:
    """Create the calendar event for a confirmed booking. Returns synced | failed | skipped. Never raises."""
    with SessionLocal() as db:
        b = db.get(Booking, booking_id)
        if not b or b.status != "confirmed" or b.calendar_status == "synced":
            return "skipped"
        conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == b.user_id))
        if not conn or conn.status != "connected":
            return "skipped"
        title = b.event.title if b.event else (b.show.movie.title if b.show else "your booking")
        err = None
        for n in range(attempts):
            try:
                insert_event(_access_token(decrypt(conn.refresh_token_enc)), build_event(b))
                b.calendar_status, b.calendar_event_id, b.calendar_synced_at = "synced", event_id(b.code), utcnow()
                notify(db, b.user_id, "Added to Google Calendar 📅",
                       f"{title} ({b.code}) is on your Google Calendar with a reminder 2 hours before.", "booking")
                break
            except Revoked:
                conn.status = "revoked"
                b.calendar_status = "failed"
                notify(db, b.user_id, "Google Calendar disconnected",
                       "We lost access to your Google Calendar, so new bookings are not being added. Reconnect it in your profile.", "booking")
                err = "revoked"
                break
            except Exception as e:  # network / 5xx: back off and retry
                err = str(e)[:200]
                if n < attempts - 1:
                    time.sleep(2 ** n)
        else:
            b.calendar_status = "failed"
            notify(db, b.user_id, "Couldn't add to Google Calendar",
                   f"{title} ({b.code}) is confirmed, but adding it to your calendar failed. You can retry from the booking page.", "booking")
        if err:
            log.warning("calendar sync failed for %s: %s", b.code, err)
        db.commit()
        return b.calendar_status or "failed"


def remove_booking(booking_id: int) -> None:
    """Best-effort removal when a booking is cancelled."""
    with SessionLocal() as db:
        b = db.get(Booking, booking_id)
        if not b or not b.calendar_event_id:
            return
        conn = db.scalar(select(CalendarConnection).where(CalendarConnection.user_id == b.user_id))
        if not conn or conn.status != "connected":
            return
        try:
            delete_event(_access_token(decrypt(conn.refresh_token_enc)), b.calendar_event_id)
            b.calendar_status, b.calendar_event_id = None, None
            db.commit()
        except Exception:
            log.warning("calendar removal failed for booking %s", booking_id)


def background(fn, *args) -> None:
    """Fire-and-forget so payment confirmation never waits on Google."""
    if not enabled():
        return
    threading.Thread(target=fn, args=args, daemon=True, name="gcal").start()


def sync_upcoming_for_user(user_id: int) -> None:
    """After connecting, add the user's future confirmed bookings that are not on the calendar yet."""
    with SessionLocal() as db:
        ids = [b.id for b in db.scalars(select(Booking).where(Booking.user_id == user_id, Booking.status == "confirmed",
                                                              Booking.calendar_status.is_(None))) if _is_future(b)]
    for i in ids:
        sync_booking(i)


def _is_future(b: Booking) -> bool:
    start = b.show.starts_at if b.show else (b.event.starts_at if b.event else None)
    return bool(start and start > utcnow())
