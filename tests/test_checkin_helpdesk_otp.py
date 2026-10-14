"""Check-in staff, support desk and OTP flows: authorisation boundaries and the guarantees they promise."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Event, Notification, OtpCode, User
from tests.conftest import login, pay, signup

API = "/api/v1"


# ------------------------------------------------------------------ helpers
def make_staff(client, admin, role, email=None):
    email = email or f"{role}{uuid.uuid4().hex[:6]}@test.example.com"
    r = client.post(f"{API}/admin/staff", headers=admin,
                    json={"email": email, "name": f"{role} person", "password": "Staff@12345", "role": role})
    assert r.status_code == 201, r.text
    return login(client, email, "Staff@12345"), email, r.json()


def make_organizer(email=None):
    email = email or f"org{uuid.uuid4().hex[:6]}@test.example.com"
    with SessionLocal() as db:
        db.add(User(email=email, name="Other Org", role="organizer", password_hash=hash_password("Organizer@123")))
        db.commit()
    return email


def own_event(event_id, organizer_email="org@test.example.com"):
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == organizer_email).one().id
        db.query(Event).filter(Event.id == event_id).update({"organizer_id": uid})
        db.commit()


def book_event(client, h, event_id, qty=2):
    tt = client.get(f"{API}/events/{event_id}").json()["ticket_types"][0]
    co = client.post(f"{API}/bookings", headers=h, json={
        "kind": "event", "idempotency_key": uuid.uuid4().hex, "event_id": event_id,
        "tickets": [{"ticket_type_id": tt["id"], "quantity": qty}]}).json()
    assert pay(client, h, co)[0].status_code == 200
    b = client.get(f"{API}/bookings/{co['booking']['id']}", headers=h).json()
    return b, f"BMS|{b['code']}|{b['qr_token']}"


def scan(client, h, event_id, qr=None, code=None):
    body = {"event_id": event_id, **({"qr": qr} if qr else {"booking_code": code})}
    return client.post(f"{API}/checkin/scan", headers=h, json=body)


def door(client, admin, event_id, organizer):
    """A check-in staff account assigned to the event by its organizer."""
    own_event(event_id)
    staff_h, email, _ = make_staff(client, admin, "checkin")
    r = client.post(f"{API}/organizer/events/{event_id}/staff", headers=organizer, json={"email": email})
    assert r.status_code == 201, r.text
    return staff_h


# ------------------------------------------------------------------ staff accounts & RBAC
def test_only_admin_creates_staff_and_emails_stay_unique(client, admin, user):
    body = {"email": "dup-staff@test.example.com", "name": "Dup Staff", "password": "Staff@12345", "role": "support"}
    assert client.post(f"{API}/admin/staff", headers=user[0], json=body).status_code == 403
    assert client.post(f"{API}/admin/staff", headers=admin, json=body).status_code == 201
    assert client.post(f"{API}/admin/staff", headers=admin, json=body).status_code == 409
    assert client.post(f"{API}/admin/staff", headers=admin, json={**body, "email": "x@test.example.com", "role": "admin"}).status_code == 422


def test_staff_roles_cannot_cross_into_other_portals(client, admin, organizer):
    chk, _, _ = make_staff(client, admin, "checkin")
    sup, _, _ = make_staff(client, admin, "support")
    for h in (chk, sup):
        assert client.get(f"{API}/admin/users", headers=h).status_code == 403
        assert client.get(f"{API}/organizer/events", headers=h).status_code == 403
        assert client.get(f"{API}/vendor/theaters", headers=h).status_code in (403, 404)
    assert client.get(f"{API}/helpdesk/tickets", headers=chk).status_code == 403
    assert client.get(f"{API}/checkin/events", headers=sup).status_code == 403
    assert client.get(f"{API}/checkin/events", headers=organizer).status_code == 403


# ------------------------------------------------------------------ check-in
def test_admit_once_then_duplicate_and_attendance_is_recorded(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    b, qr = book_event(client, user[0], event, qty=2)

    r = scan(client, staff, event, qr=qr)
    assert r.status_code == 200 and r.json()["result"] == "admitted" and r.json()["tickets"] == 2
    again = scan(client, staff, event, qr=qr).json()
    assert again["result"] == "duplicate" and again["checked_in_at"]

    stats = client.get(f"{API}/checkin/events/{event}/stats", headers=staff).json()
    assert stats["tickets_sold"] == 2 and stats["tickets_admitted"] == 2 and stats["bookings_arrived"] == 1
    assert [x["result"] for x in stats["recent"]] == ["duplicate", "admitted"]

    att = client.get(f"{API}/organizer/events/{event}/attendees", headers=organizer).json()
    assert att["total"] == 1 and att["items"][0]["checked_in_at"] and att["summary"]["tickets_admitted"] == 2
    assert client.get(f"{API}/organizer/events/{event}/attendees?arrived=false", headers=organizer).json()["total"] == 0


def test_concurrent_scans_of_one_ticket_admit_exactly_once(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    _, qr = book_event(client, user[0], event, qty=1)
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: scan(client, staff, event, qr=qr).json()["result"], range(8)))
    assert results.count("admitted") == 1 and results.count("duplicate") == 7


def test_admitted_ticket_cannot_then_be_cancelled_for_a_refund(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    b, qr = book_event(client, user[0], event, qty=1)
    assert scan(client, staff, event, qr=qr).json()["result"] == "admitted"
    r = client.post(f"{API}/bookings/{b['id']}/cancel", headers=user[0])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_checked_in"
    assert client.get(f"{API}/bookings/{b['id']}", headers=user[0]).json()["status"] == "confirmed"


def test_forged_and_malformed_codes_are_rejected(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    b, _ = book_event(client, user[0], event, qty=1)
    assert scan(client, staff, event, qr=f"BMS|{b['code']}|not-the-token").json()["result"] == "invalid"
    assert scan(client, staff, event, qr="hello world").json()["result"] == "invalid"
    assert scan(client, staff, event, qr="BMS|NOSUCHCODE|abc").json()["result"] == "invalid"
    # nothing above admitted the party
    assert client.get(f"{API}/checkin/events/{event}/stats", headers=staff).json()["tickets_admitted"] == 0


def test_manual_code_entry_works_and_is_marked_manual(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    b, _ = book_event(client, user[0], event, qty=1)
    assert scan(client, staff, event, code=b["code"].lower()).json()["result"] == "admitted"
    recent = client.get(f"{API}/checkin/events/{event}/stats", headers=staff).json()["recent"]
    assert recent[0]["method"] == "manual"


def test_cancelled_booking_and_other_event_ticket_are_refused(client, admin, organizer, user, event):
    staff = door(client, admin, event, organizer)
    b, qr = book_event(client, user[0], event, qty=1)
    assert client.post(f"{API}/bookings/{b['id']}/cancel", headers=user[0]).status_code == 200
    assert scan(client, staff, event, qr=qr).json()["result"] == "not_confirmed"

    other_event_id = event + 1
    # a ticket for a *different* event, scanned at this door
    with SessionLocal() as db:
        src = db.get(Event, event)
        e2 = Event(title="Other", slug=f"other-{uuid.uuid4().hex[:6]}", section="events", category_id=src.category_id,
                   city_id=src.city_id, venue_name="Hall", status="approved",
                   starts_at=datetime.now(timezone.utc) + timedelta(days=3), organizer_id=src.organizer_id)
        from app.models import TicketType
        e2.ticket_types.append(TicketType(name="GA", price_paise=10000, total=5, max_per_booking=5))
        db.add(e2)
        db.commit()
        other_event_id = e2.id
    b2, qr2 = book_event(client, user[0], other_event_id, qty=1)
    r = scan(client, staff, event, qr=qr2).json()
    assert r["result"] == "wrong_event"
    assert client.get(f"{API}/bookings/{b2['id']}", headers=user[0]).json()["status"] == "confirmed"


def test_staff_only_see_and_scan_assigned_events(client, admin, organizer, user, event):
    assigned = door(client, admin, event, organizer)
    stranger, _, _ = make_staff(client, admin, "checkin")  # a checkin account with no assignment
    _, qr = book_event(client, user[0], event, qty=1)

    assert scan(client, stranger, event, qr=qr).status_code == 404
    assert client.get(f"{API}/checkin/events/{event}/stats", headers=stranger).status_code == 404
    assert all(e["id"] != event for e in client.get(f"{API}/checkin/events", headers=stranger).json())
    assert any(e["id"] == event for e in client.get(f"{API}/checkin/events", headers=assigned).json())


def test_organizer_ownership_for_staff_and_attendees(client, admin, organizer, event):
    own_event(event)
    rival = login(client, make_organizer(), "Organizer@123")
    _, email, _ = make_staff(client, admin, "checkin")
    assert client.post(f"{API}/organizer/events/{event}/staff", headers=rival, json={"email": email}).status_code == 404
    assert client.get(f"{API}/organizer/events/{event}/attendees", headers=rival).status_code == 404
    assert client.get(f"{API}/organizer/events/{event}/staff", headers=rival).status_code == 404
    # assigning a plain customer (or an unknown address) gives the same answer, so accounts cannot be probed
    cust_email = signup(client)[1]["email"]
    a = client.post(f"{API}/organizer/events/{event}/staff", headers=organizer, json={"email": cust_email})
    b = client.post(f"{API}/organizer/events/{event}/staff", headers=organizer, json={"email": "nobody@test.example.com"})
    assert a.status_code == b.status_code == 404 and a.json()["error"]["message"] == b.json()["error"]["message"]
    # assign then remove
    assert len(client.post(f"{API}/organizer/events/{event}/staff", headers=organizer, json={"email": email}).json()) == 1
    sid = client.get(f"{API}/organizer/events/{event}/staff", headers=organizer).json()[0]["id"]
    assert client.delete(f"{API}/organizer/events/{event}/staff/{sid}", headers=organizer).json() == []


# ------------------------------------------------------------------ support desk
def open_ticket(client, user_h, user_email, **extra):
    r = client.post(f"{API}/support/tickets", headers=user_h, json={
        "email": user_email, "subject": "Charged twice for my booking", "message": "I was charged twice, please check.", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_agent_works_ticket_and_customer_sees_only_public_messages(client, admin, user):
    h, me = user
    agent, _, _ = make_staff(client, admin, "support")
    tid = open_ticket(client, h, me["email"], category="payment")

    q = client.get(f"{API}/helpdesk/tickets?status=active&assigned=unassigned", headers=agent).json()
    assert any(t["id"] == tid for t in q["items"])

    assert client.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=agent,
                       json={"body": "Checking with the payment team.", "internal": True}).status_code == 201
    assert client.post(f"{API}/helpdesk/tickets/{tid}/messages", headers=agent,
                       json={"body": "We found the duplicate charge and are fixing it."}).status_code == 201
    t = client.get(f"{API}/helpdesk/tickets/{tid}", headers=agent).json()
    assert t["status"] == "in_progress" and t["assigned_to"] and len(t["messages"]) == 2

    mine = client.get(f"{API}/support/tickets/{tid}", headers=h).json()
    assert [m["body"] for m in mine["messages"]] == ["We found the duplicate charge and are fixing it."]
    assert "Checking with the payment team" not in str(mine)

    assert client.post(f"{API}/support/tickets/{tid}/messages", headers=h, json={"body": "Thank you!"}).status_code == 201
    assert client.patch(f"{API}/helpdesk/tickets/{tid}", headers=agent, json={"status": "resolved", "priority": "low"}).status_code == 200
    # a customer reply re-opens a resolved ticket
    client.post(f"{API}/support/tickets/{tid}/messages", headers=h, json={"body": "Still not refunded"})
    assert client.get(f"{API}/helpdesk/tickets/{tid}", headers=agent).json()["status"] == "open"
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == me["id"], Notification.kind == "support").count() >= 1


def test_customers_cannot_read_other_peoples_tickets_or_use_the_desk(client, user, user2):
    tid = open_ticket(client, user[0], user[1]["email"])
    assert client.get(f"{API}/support/tickets/{tid}", headers=user2[0]).status_code == 404
    assert client.post(f"{API}/support/tickets/{tid}/messages", headers=user2[0], json={"body": "hi"}).status_code == 404
    assert client.get(f"{API}/helpdesk/tickets", headers=user[0]).status_code == 403
    assert client.get(f"{API}/helpdesk/bookings/lookup?code=ABCD1234", headers=user[0]).status_code == 403


def test_booking_lookup_never_leaks_qr_token_and_foreign_booking_codes_are_not_attached(client, admin, user, user2, event):
    agent, _, _ = make_staff(client, admin, "support")
    b, qr = book_event(client, user2[0], event, qty=1)  # user2's booking

    r = client.get(f"{API}/helpdesk/bookings/lookup?code={b['code']}", headers=agent)
    assert r.status_code == 200 and r.json()["customer"]["email"] == user2[1]["email"]
    assert b["qr_token"] not in r.text and "qr_token" not in r.text
    assert client.get(f"{API}/helpdesk/bookings/lookup?code=ZZZZZZZZ", headers=agent).status_code == 404

    # user (not the owner) cites user2's booking code: the agent view must not expose that booking
    tid = open_ticket(client, user[0], user[1]["email"], booking_code=b["code"])
    t = client.get(f"{API}/helpdesk/tickets/{tid}", headers=agent).json()
    assert t["booking"] is None
    # the owner citing their own code does get the context
    tid2 = open_ticket(client, user2[0], user2[1]["email"], booking_code=b["code"])
    assert client.get(f"{API}/helpdesk/tickets/{tid2}", headers=agent).json()["booking"]["code"] == b["code"]


def test_refund_escalation_notifies_admins_and_agents_cannot_cancel(client, admin, user, event):
    agent, _, _ = make_staff(client, admin, "support")
    b, _ = book_event(client, user[0], event, qty=1)
    tid = open_ticket(client, user[0], user[1]["email"], booking_code=b["code"])
    assert client.post(f"{API}/helpdesk/tickets/{tid}/escalate-refund", headers=agent, json={"reason": "short"}).status_code == 422
    r = client.post(f"{API}/helpdesk/tickets/{tid}/escalate-refund", headers=agent, json={"reason": "Customer was double charged"})
    assert r.status_code == 200 and r.json()["status"] == "escalated"
    t = client.get(f"{API}/helpdesk/tickets/{tid}", headers=agent).json()
    assert t["category"] == "refund" and t["priority"] == "high"
    with SessionLocal() as db:
        assert db.query(Notification).join(User, User.id == Notification.user_id).filter(
            User.role == "admin", Notification.title.like(f"Refund escalation: ticket #{tid}")).count() >= 1
    # the money-moving endpoints stay admin-only
    assert client.post(f"{API}/bookings/{b['id']}/cancel", headers=agent).status_code == 404  # only owner/admin may cancel
    assert client.patch(f"{API}/admin/support/{tid}", headers=agent, json={"status": "resolved"}).status_code == 403
    assert client.patch(f"{API}/admin/support/{tid}", headers=admin, json={"status": "resolved", "admin_reply": "Refunded."}).status_code == 200
    assert client.get(f"{API}/support/tickets/{tid}", headers=user[0]).json()["messages"][-1]["body"] == "Refunded."


# ------------------------------------------------------------------ OTP: email verification & password reset
def test_email_verification_flow(client):
    h, me = signup(client)
    assert me["email_verified"] is False
    sent = client.post(f"{API}/users/me/email/send-code", headers=h).json()
    code = sent["dev_code"]
    assert code and len(code) == 6
    assert client.post(f"{API}/users/me/email/send-code", headers=h).status_code == 429  # resend throttle
    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"{API}/users/me/email/verify", headers=h, json={"code": wrong}).status_code == 400
    r = client.post(f"{API}/users/me/email/verify", headers=h, json={"code": code})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert client.post(f"{API}/users/me/email/verify", headers=h, json={"code": code}).status_code == 400  # single use
    assert client.post(f"{API}/users/me/email/send-code", headers=h).status_code == 409  # already verified


def test_code_is_burned_after_too_many_wrong_guesses(client):
    h, me = signup(client)
    code = client.post(f"{API}/users/me/email/send-code", headers=h).json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post(f"{API}/users/me/email/verify", headers=h, json={"code": wrong}).status_code == 400
    assert client.post(f"{API}/users/me/email/verify", headers=h, json={"code": code}).status_code == 400  # even the right one


def test_expired_code_is_rejected_and_codes_are_not_stored_in_clear(client):
    h, me = signup(client)
    code = client.post(f"{API}/users/me/email/send-code", headers=h).json()["dev_code"]
    with SessionLocal() as db:
        row = db.query(OtpCode).filter(OtpCode.email == me["email"]).one()
        assert code not in row.code_hash and len(row.code_hash) == 64
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post(f"{API}/users/me/email/verify", headers=h, json={"code": code}).status_code == 400


def test_password_reset_flow_and_no_account_enumeration(client):
    h, me = signup(client)
    known = client.post(f"{API}/auth/password/forgot", json={"email": me["email"]})
    unknown = client.post(f"{API}/auth/password/forgot", json={"email": "ghost@test.example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]
    assert unknown.json()["dev_code"] is None

    code = known.json()["dev_code"]
    bad = client.post(f"{API}/auth/password/reset", json={"email": me["email"], "code": "123456" if code != "123456" else "654321", "new_password": "BrandNew123"})
    assert bad.status_code == 400
    ok = client.post(f"{API}/auth/password/reset", json={"email": me["email"], "code": code, "new_password": "BrandNew123"})
    assert ok.status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": me["email"], "password": "Passw0rdX"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": me["email"], "password": "BrandNew123"}).status_code == 200
    # the code cannot be replayed, and a code for one address cannot reset another
    assert client.post(f"{API}/auth/password/reset", json={"email": me["email"], "code": code, "new_password": "Another1234"}).status_code == 400
    other = signup(client)[1]["email"]
    assert client.post(f"{API}/auth/password/reset", json={"email": other, "code": code, "new_password": "Another1234"}).status_code == 400
