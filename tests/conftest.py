import os
import uuid
from datetime import datetime, timedelta, timezone

# Must be set before the app is imported
os.environ.update(
    ENV="test",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://bms@localhost:54329/bookmyshow_test"),
    JWT_SECRET="test-secret-test-secret-test-secret-123",
    RAZORPAY_KEY_ID="rzp_test_unit",
    RAZORPAY_KEY_SECRET="unit-test-secret",
    RAZORPAY_WEBHOOK_SECRET="unit-webhook-secret",
    GOOGLE_CLIENT_ID="",
    SMTP_HOST="",  # never send real mail from tests, whatever the developer's .env says
)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password, hmac_sha256
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import City, Event, EventCategory, Language, Movie, Screen, Show, TicketType, User, Venue
from app.seed import seed_movies, seed_reference
from app.services import razorpay
from app.services import seats as seat_svc


@pytest.fixture(scope="session", autouse=True)
def database():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")  # also proves the migrations work from scratch
    with SessionLocal() as db:
        seed_reference(db)
        seed_movies(db)
        db.add(User(email="admin@test.example.com", name="Admin", role="admin", password_hash=hash_password("Admin@12345")))
        db.add(User(email="org@test.example.com", name="Org", role="organizer", password_hash=hash_password("Organizer@123")))
        db.commit()
    yield


@pytest.fixture(autouse=True)
def fake_gateway(monkeypatch):
    monkeypatch.setattr(razorpay, "create_order",
                        lambda amount, receipt, notes=None: {"id": "order_" + uuid.uuid4().hex[:14], "amount": amount})
    monkeypatch.setattr(razorpay, "refund_payment",
                        lambda pid, amount, notes=None: {"id": "rfnd_" + uuid.uuid4().hex[:10], "amount": amount})


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def signup(client, email=None, name="Tester"):
    email = email or f"u{uuid.uuid4().hex[:8]}@test.example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "name": name, "password": "Passw0rdX"})
    assert r.status_code == 201, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['access_token']}"}, d["user"]


@pytest.fixture
def user(client):
    return signup(client)


@pytest.fixture
def user2(client):
    return signup(client)


def login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin@test.example.com", "Admin@12345")


@pytest.fixture
def organizer(client):
    return login(client, "org@test.example.com", "Organizer@123")


@pytest.fixture
def show():
    """A fresh show on a 2x5 screen starting in 2 days (Gold 5 seats @300, Silver 5 seats @200)."""
    with SessionLocal() as db:
        city = db.query(City).first()
        v = Venue(name=f"Test Cinema {uuid.uuid4().hex[:6]}", type="cinema", city_id=city.id, address="Test Road")
        db.add(v)
        db.flush()
        scr = Screen(venue_id=v.id, name="S1", layout={"rows": [
            {"label": "A", "category": "Gold", "seats": 5, "aisles": []},
            {"label": "B", "category": "Silver", "seats": 5, "aisles": []}]})
        db.add(scr)
        db.flush()
        seat_svc.build_seats(db, scr)
        movie = db.query(Movie).first()
        lang = db.query(Language).first()
        start = datetime.now(timezone.utc) + timedelta(days=2)
        sh = Show(screen_id=scr.id, movie_id=movie.id, language_id=lang.id, starts_at=start,
                  ends_at=start + timedelta(hours=3), prices={"Gold": 30000, "Silver": 20000})
        db.add(sh)
        db.flush()
        seat_svc.materialize_show_seats(db, sh)
        db.commit()
        return sh.id


@pytest.fixture
def event():
    with SessionLocal() as db:
        cat = db.query(EventCategory).filter_by(section="events").first()
        city = db.query(City).first()
        e = Event(title=f"Test Event {uuid.uuid4().hex[:5]}", slug=f"test-event-{uuid.uuid4().hex[:8]}", section="events",
                  category_id=cat.id, city_id=city.id, venue_name="Hall",
                  starts_at=datetime.now(timezone.utc) + timedelta(days=5), status="approved")
        e.ticket_types.append(TicketType(name="General", price_paise=50000, total=5, max_per_booking=5))
        db.add(e)
        db.commit()
        return e.id


def seat_ids(client, show_id, n=2, category=None, headers=None):
    r = client.get(f"/api/v1/shows/{show_id}", headers=headers or {})
    assert r.status_code == 200
    seats = [s for s in r.json()["seats"] if s["status"] == "available" and (not category or s["category"] == category)]
    return [s["id"] for s in seats[:n]]


def pay(client, headers, checkout):
    """Simulate Razorpay Checkout success for a CheckoutOut / GiftCardCheckout and call verify."""
    rz = checkout["razorpay"]
    pid = "pay_" + uuid.uuid4().hex[:14]
    sig = hmac_sha256("unit-test-secret", f"{rz['order_id']}|{pid}")
    return client.post("/api/v1/payments/verify", headers=headers, json={
        "razorpay_order_id": rz["order_id"], "razorpay_payment_id": pid, "razorpay_signature": sig}), pid
