"""Google Calendar sync. Google's HTTP endpoints are stubbed; everything else (DB, hooks, notifications, crypto) is real."""
import pytest

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Booking, CalendarConnection, Notification
from app.services import gcal
from tests.test_checkin_helpdesk_otp import book_event

API = "/api/v1"


@pytest.fixture(autouse=True)
def google(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(gcal, "background", lambda fn, *a: fn(*a))  # run the sync inline instead of in a thread
    monkeypatch.setattr(gcal.time, "sleep", lambda s: None)
    calls = {"insert": [], "delete": [], "token": 0}
    monkeypatch.setattr(gcal, "_access_token", lambda rt: calls.__setitem__("token", calls["token"] + 1) or "access-token")
    monkeypatch.setattr(gcal, "insert_event", lambda at, body: calls["insert"].append(body))
    monkeypatch.setattr(gcal, "delete_event", lambda at, gid: calls["delete"].append(gid))
    return calls


def connect_user(user_id, status="connected"):
    with SessionLocal() as db:
        db.add(CalendarConnection(user_id=user_id, refresh_token_enc=gcal.encrypt("refresh-token-secret"), status=status))
        db.commit()


def notes(user_id):
    with SessionLocal() as db:
        return [n.title for n in db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.id)]


def booking_row(booking_id):
    with SessionLocal() as db:
        b = db.get(Booking, booking_id)
        return b.calendar_status, b.calendar_event_id


def test_confirmed_booking_is_added_once_and_user_is_notified(client, user, event, google):
    h, me = user
    connect_user(me["id"])
    b, _ = book_event(client, h, event, qty=2)
    assert len(google["insert"]) == 1
    ev = google["insert"][0]
    assert ev["id"] == gcal.event_id(b["code"]) and b["code"] in ev["description"] and ev["summary"].startswith("🎟️")
    assert ev["start"]["dateTime"] and ev["reminders"]["overrides"][0]["minutes"] == 120
    assert booking_row(b["id"]) == ("synced", gcal.event_id(b["code"]))
    assert "Added to Google Calendar 📅" in notes(me["id"])
    assert client.get(f"{API}/bookings/{b['id']}", headers=h).json()["calendar_status"] == "synced"
    assert gcal.sync_booking(b["id"]) == "skipped" and len(google["insert"]) == 1  # idempotent


def test_nothing_happens_without_a_connection(client, user, event, google):
    b, _ = book_event(client, user[0], event)
    assert google["insert"] == [] and booking_row(b["id"]) == (None, None)
    assert "Added to Google Calendar 📅" not in notes(user[1]["id"])


def test_revoked_access_marks_connection_and_tells_the_user(client, user, event, google, monkeypatch):
    def boom(rt):
        raise gcal.Revoked("invalid_grant")
    monkeypatch.setattr(gcal, "_access_token", boom)
    h, me = user
    connect_user(me["id"])
    b, _ = book_event(client, h, event)
    assert booking_row(b["id"])[0] == "failed"
    assert client.get(f"{API}/calendar/status", headers=h).json()["needs_reconnect"] is True
    assert "Google Calendar disconnected" in notes(me["id"])
    # a revoked connection is not retried for later bookings
    assert gcal.sync_booking(b["id"]) == "skipped"


def test_transient_failure_retries_then_fails_and_can_be_retried(client, user, event, google, monkeypatch):
    h, me = user
    connect_user(me["id"])
    attempts = []

    def flaky(at, body):
        attempts.append(1)
        raise RuntimeError("503 from Google")
    monkeypatch.setattr(gcal, "insert_event", flaky)
    b, _ = book_event(client, h, event)
    assert len(attempts) == 3 and booking_row(b["id"])[0] == "failed"
    assert "Couldn't add to Google Calendar" in notes(me["id"])
    # payment/booking is unaffected by the calendar failure
    assert client.get(f"{API}/bookings/{b['id']}", headers=h).json()["status"] == "confirmed"
    monkeypatch.setattr(gcal, "insert_event", lambda at, body: google["insert"].append(body))
    r = client.post(f"{API}/bookings/{b['id']}/calendar", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "synced" and booking_row(b["id"])[0] == "synced"


def test_cancelling_removes_the_calendar_event(client, user, event, google):
    h, me = user
    connect_user(me["id"])
    b, _ = book_event(client, h, event)
    assert client.post(f"{API}/bookings/{b['id']}/cancel", headers=h).status_code == 200
    assert google["delete"] == [gcal.event_id(b["code"])] and booking_row(b["id"]) == (None, None)


def test_retry_endpoint_is_owner_only_and_needs_a_connection(client, user, user2, event):
    b, _ = book_event(client, user[0], event)
    assert client.post(f"{API}/bookings/{b['id']}/calendar", headers=user2[0]).status_code == 404
    assert client.post(f"{API}/bookings/{b['id']}/calendar", headers=user[0]).status_code == 409


def test_connect_url_callback_and_encrypted_storage(client, user, monkeypatch):
    h, me = user
    url = client.post(f"{API}/calendar/connect", headers=h).json()["url"]
    assert url.startswith(gcal.AUTH_URL) and "access_type=offline" in url and "calendar.events" in url and "client_id=client-id" in url
    state = url.split("state=")[1].split("&")[0]
    monkeypatch.setattr(gcal, "exchange_code", lambda code: "refresh-token-secret")
    monkeypatch.setattr(gcal, "sync_upcoming_for_user", lambda uid: None)

    ok = client.get(f"{API}/calendar/callback", params={"state": state, "code": "abc"}, follow_redirects=False)
    assert ok.status_code == 302 and ok.headers["location"].endswith("/account/profile?calendar=connected")
    with SessionLocal() as db:
        row = db.query(CalendarConnection).filter_by(user_id=me["id"]).one()
        assert "refresh-token-secret" not in row.refresh_token_enc and gcal.decrypt(row.refresh_token_enc) == "refresh-token-secret"
    assert client.get(f"{API}/calendar/status", headers=h).json()["connected"] is True

    denied = client.get(f"{API}/calendar/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
    assert denied.headers["location"].endswith("calendar=denied")
    forged = client.get(f"{API}/calendar/callback", params={"state": "not-a-jwt", "code": "abc"}, follow_redirects=False)
    assert forged.headers["location"].endswith("calendar=expired")

    assert client.delete(f"{API}/calendar", headers=h).status_code == 200
    assert client.get(f"{API}/calendar/status", headers=h).json()["connected"] is False


def test_connect_unavailable_when_google_is_not_configured(client, user, monkeypatch):
    monkeypatch.setattr(settings, "google_client_secret", "")
    assert client.post(f"{API}/calendar/connect", headers=user[0]).status_code == 503
    assert client.post(f"{API}/calendar/connect").status_code == 401
