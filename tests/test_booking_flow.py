import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.core.security import hmac_sha256
from app.db.session import SessionLocal
from app.models import Booking, OrganizerProfile, Show, TicketType, User
from app.services import booking as bsvc
from app.services import seats as seat_svc
from tests.conftest import pay, seat_ids, signup

API = "/api/v1"


def lock(client, h, show, ids):
    return client.put(f"{API}/shows/{show}/locks", headers=h, json={"seat_ids": ids})


def checkout(client, h, show, ids, **extra):
    return client.post(f"{API}/bookings", headers=h, json={
        "kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show, "seat_ids": ids, **extra})


def expire_now(booking_id):
    with SessionLocal() as db:
        db.query(Booking).filter(Booking.id == booking_id).update({"expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)})
        db.commit()
        bsvc.expire_pending_bookings(db)
        bsvc.commit(db)


def test_two_users_cannot_hold_the_same_seat(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 2)
    assert lock(client, h1, show, ids).status_code == 200
    r = lock(client, h2, show, ids[:1])
    assert r.status_code == 409 and r.json()["error"]["code"] == "seat_unavailable"
    s2 = {s["id"]: s for s in client.get(f"{API}/shows/{show}", headers=h2).json()["seats"]}
    s1 = {s["id"]: s for s in client.get(f"{API}/shows/{show}", headers=h1).json()["seats"]}
    assert s2[ids[0]]["status"] == "locked" and not s2[ids[0]]["mine"]
    assert s1[ids[0]]["mine"]
    assert client.delete(f"{API}/shows/{show}/locks", headers=h1).status_code == 200
    assert lock(client, h2, show, ids).status_code == 200


def test_lock_replaces_previous_selection(client, user, show):
    h, _ = user
    a = seat_ids(client, show, 4)
    lock(client, h, show, a[:2])
    lock(client, h, show, a[2:4])
    seats = {s["id"]: s for s in client.get(f"{API}/shows/{show}", headers=h).json()["seats"]}
    assert seats[a[0]]["status"] == "available" and seats[a[2]]["mine"]


def test_full_payment_flow_and_idempotency(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 2, "Gold")
    lock(client, h, show, ids)
    body = {"kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show, "seat_ids": ids}
    r = client.post(f"{API}/bookings", headers=h, json=body)
    assert r.status_code == 201, r.text
    co = r.json()
    b = co["booking"]
    assert b["status"] == "pending" and b["subtotal_paise"] == 60000
    assert b["fee_paise"] == 1800 and b["tax_paise"] == 324  # 3% fee, 18% GST on the fee
    assert b["total_paise"] == 62124 and co["razorpay"]["amount"] == 62124
    r2 = client.post(f"{API}/bookings", headers=h, json=body).json()  # retry with same key
    assert r2["booking"]["id"] == b["id"] and r2["razorpay"]["order_id"] == co["razorpay"]["order_id"]

    bad = client.post(f"{API}/payments/verify", headers=h, json={
        "razorpay_order_id": co["razorpay"]["order_id"], "razorpay_payment_id": "pay_x", "razorpay_signature": "0" * 64})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_signature"

    r, pid = pay(client, h, co)
    assert r.status_code == 200, r.text
    assert r.json()["booking"]["status"] == "confirmed" and r.json()["booking"]["qr_token"]
    sig = hmac_sha256("unit-test-secret", f"{co['razorpay']['order_id']}|{pid}")
    again = client.post(f"{API}/payments/verify", headers=h, json={
        "razorpay_order_id": co["razorpay"]["order_id"], "razorpay_payment_id": pid, "razorpay_signature": sig})
    assert again.status_code == 200 and again.json()["booking"]["id"] == b["id"]

    seats = {s["id"]: s for s in client.get(f"{API}/shows/{show}").json()["seats"]}
    assert all(seats[i]["status"] == "booked" for i in ids)
    assert client.get(f"{API}/bookings", headers=h).json()["total"] == 1
    assert client.get(f"{API}/payments", headers=h).json()["items"][0]["status"] == "paid"


def test_other_users_cannot_pay_or_read_my_booking(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 1)
    lock(client, h1, show, ids)
    co = checkout(client, h1, show, ids).json()
    r, _ = pay(client, h2, co)
    assert r.status_code == 404
    assert client.get(f"{API}/bookings/{co['booking']['id']}", headers=h2).status_code == 404


def test_cannot_book_seats_you_do_not_hold(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 1)
    lock(client, h1, show, ids)
    assert checkout(client, h2, show, ids).status_code == 409


def test_concurrent_lock_race_has_single_winner(client, show):
    ids = seat_ids(client, show, 1)
    users = [signup(client)[1]["id"] for _ in range(12)]
    barrier = threading.Barrier(len(users))

    def attempt(uid):
        with SessionLocal() as db:
            s = db.get(Show, show)
            barrier.wait()
            try:
                seat_svc.set_locks(db, uid, s, ids)
                db.commit()
                return "won"
            except AppError as e:
                db.rollback()
                return e.code

    with ThreadPoolExecutor(len(users)) as ex:
        results = list(ex.map(attempt, users))
    assert results.count("won") == 1 and results.count("seat_unavailable") == len(users) - 1


def test_expired_hold_is_released_and_booking_expires(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 2)
    lock(client, h1, show, ids[:1])
    co = checkout(client, h1, show, ids[:1]).json()
    expire_now(co["booking"]["id"])
    assert lock(client, h2, show, ids[:1]).status_code == 200  # seat is free again
    assert client.get(f"{API}/bookings/{co['booking']['id']}", headers=h1).json()["status"] == "expired"


def test_late_payment_after_seat_was_taken_is_refunded(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 1)
    lock(client, h1, show, ids)
    co = checkout(client, h1, show, ids).json()
    expire_now(co["booking"]["id"])
    lock(client, h2, show, ids)  # someone else grabs it
    r, _ = pay(client, h1, co)
    assert r.status_code == 409 and r.json()["error"]["code"] == "booking_failed_refunded"
    assert client.get(f"{API}/payments", headers=h1).json()["items"][0]["status"] == "refunded"
    assert client.get(f"{API}/bookings/{co['booking']['id']}", headers=h1).json()["status"] == "failed"


def test_late_payment_with_seat_still_free_is_honoured(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 1)
    lock(client, h, show, ids)
    co = checkout(client, h, show, ids).json()
    expire_now(co["booking"]["id"])
    r, _ = pay(client, h, co)
    assert r.status_code == 200 and r.json()["booking"]["status"] == "confirmed"


def test_cancel_refunds_ticket_value_and_frees_seats(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 2, "Silver")
    lock(client, h, show, ids)
    co = checkout(client, h, show, ids).json()
    pay(client, h, co)
    r = client.post(f"{API}/bookings/{co['booking']['id']}/cancel", headers=h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "cancelled" and b["refund_paise"] == 40000  # fee + tax are non-refundable
    free = [s for s in client.get(f"{API}/shows/{show}").json()["seats"] if s["id"] in ids]
    assert all(s["status"] == "available" for s in free)
    assert client.post(f"{API}/bookings/{co['booking']['id']}/cancel", headers=h).status_code == 409


def test_gift_card_purchase_and_full_cover_checkout(client, user, show):
    h, _ = user
    gc = client.post(f"{API}/gift-cards", headers=h, json={
        "amount_paise": 50000, "recipient_name": "Pal", "recipient_email": "pal@test.example.com"})
    assert gc.status_code == 201
    r, _ = pay(client, h, gc.json())
    code = r.json()["gift_card_code"]
    assert code and code.startswith("GC")
    ids = seat_ids(client, show, 1, "Silver")
    lock(client, h, show, ids)
    r = checkout(client, h, show, ids, gift_card_code=code)
    assert r.status_code == 201
    b = r.json()["booking"]
    assert b["gift_card_paise"] == b["total_paise"] == 20708 and r.json()["razorpay"] is None
    assert b["status"] == "confirmed"  # nothing left to pay
    assert client.get(f"{API}/gift-cards/check/{code}", headers=h).json()["balance_paise"] == 50000 - 20708
    # cancelling restores the ticket value to the gift card
    client.post(f"{API}/bookings/{b['id']}/cancel", headers=h)
    assert client.get(f"{API}/gift-cards/check/{code}", headers=h).json()["balance_paise"] == 50000 - 20708 + 20000


def test_coupon_rules(client, user, admin, show):
    h, _ = user
    code = "ONE" + uuid.uuid4().hex[:5].upper()
    mk = client.post(f"{API}/admin/coupons", headers=admin, json={
        "code": code, "title": "Flat", "discount_type": "flat", "value": 5000, "per_user_limit": 1})
    assert mk.status_code == 201
    assert client.post(f"{API}/coupons/validate", headers=h,
                       json={"code": "NOPE", "kind": "movie", "subtotal_paise": 1000}).status_code == 400
    ids = seat_ids(client, show, 2, "Gold")
    lock(client, h, show, ids[:1])
    co = checkout(client, h, show, ids[:1], coupon_code=code).json()
    assert co["booking"]["discount_paise"] == 5000
    lock(client, h, show, ids)
    assert checkout(client, h, show, ids, coupon_code=code).status_code == 400  # per-user limit while first is reserved
    expire_now(co["booking"]["id"])  # redemption is released with the booking
    lock(client, h, show, ids[:1])
    assert checkout(client, h, show, ids[:1], coupon_code=code).status_code == 201


def test_event_inventory_cannot_be_oversold(client, event):
    heads = [signup(client)[0] for _ in range(8)]  # 8 buyers, 5 tickets in stock
    tt_id = client.get(f"{API}/events/{event}").json()["ticket_types"][0]["id"]

    def buy(h):
        return client.post(f"{API}/bookings", headers=h, json={
            "kind": "event", "idempotency_key": uuid.uuid4().hex, "event_id": event,
            "tickets": [{"ticket_type_id": tt_id, "quantity": 1}]}).status_code

    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(buy, heads))
    assert codes.count(201) == 5 and codes.count(409) == 3
    ev = client.get(f"{API}/events/{event}").json()
    assert ev["ticket_types"][0]["available"] == 0 and ev["sold_out"]


def test_event_booking_confirm_then_cancel_restores_inventory(client, user, event):
    h, _ = user
    tt = client.get(f"{API}/events/{event}").json()["ticket_types"][0]
    co = client.post(f"{API}/bookings", headers=h, json={
        "kind": "event", "idempotency_key": uuid.uuid4().hex, "event_id": event,
        "tickets": [{"ticket_type_id": tt["id"], "quantity": 2}]}).json()
    pay(client, h, co)
    t = client.get(f"{API}/events/{event}").json()["ticket_types"][0]
    assert t["sold"] == 2 and t["held"] == 0
    client.post(f"{API}/bookings/{co['booking']['id']}/cancel", headers=h)
    assert client.get(f"{API}/events/{event}").json()["ticket_types"][0]["sold"] == 0


def test_webhook_signature_and_idempotent_confirmation(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 1)
    lock(client, h, show, ids)
    co = checkout(client, h, show, ids).json()
    payload = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_wh_" + uuid.uuid4().hex[:8], "order_id": co["razorpay"]["order_id"], "method": "upi"}}}}).encode()
    bad = client.post(f"{API}/payments/webhook", content=payload, headers={"X-Razorpay-Signature": "bad"})
    assert bad.status_code == 400
    sig = hmac_sha256("unit-webhook-secret", payload)
    for _ in range(2):  # Razorpay retries: must be safe
        assert client.post(f"{API}/payments/webhook", content=payload, headers={"X-Razorpay-Signature": sig}).status_code == 200
    assert client.get(f"{API}/bookings/{co['booking']['id']}", headers=h).json()["status"] == "confirmed"


def test_organizer_event_review_flow(client, organizer, admin):
    cat = client.get(f"{API}/categories?section=events").json()[0]
    city = client.get(f"{API}/cities").json()[0]
    body = {"title": "Org Test Gig", "section": "events", "category_id": cat["id"], "city_id": city["id"],
            "starts_at": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat(),
            "ticket_types": [{"name": "GA", "price_paise": 10000, "total": 10}]}
    with SessionLocal() as db:
        u = db.query(User).filter_by(email="org@test.example.com").one()
        if not db.query(OrganizerProfile).filter_by(user_id=u.id).first():
            db.add(OrganizerProfile(user_id=u.id, company_name="Org", contact_phone="+919999999998", status="approved"))
            db.commit()
    r = client.post(f"{API}/organizer/events", headers=organizer, json=body)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["status"] == "pending"
    assert client.get(f"{API}/events/{ev['id']}").status_code == 404  # hidden until approved
    assert client.patch(f"{API}/admin/events/{ev['id']}", headers=admin, json={"status": "approved"}).status_code == 200
    assert client.get(f"{API}/events/{ev['id']}").status_code == 200
    a = client.get(f"{API}/organizer/analytics", headers=organizer)
    assert a.status_code == 200 and "daily" in a.json()
