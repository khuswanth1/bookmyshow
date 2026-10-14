import uuid
from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models import Show
from tests.conftest import pay, signup

API = "/api/v1"
LAYOUT = {"rows": [{"label": "A", "category": "Gold", "seats": 3, "aisles": []},
                   {"label": "B", "category": "Silver", "seats": 3, "aisles": []}]}
PRICES = {"Gold": 30000, "Silver": 20000}


def vendor_applicant(client):
    h, u = signup(client)
    r = client.post(f"{API}/vendor/register", headers=h, json={
        "business_name": f"Vendor {uuid.uuid4().hex[:5]}", "contact_phone": "+919999900000", "pan_number": "ABCDE1234F"})
    assert r.status_code == 201, r.text
    return h, u, r.json()


def approved_vendor(client, admin, commission=None):
    h, u, vp = vendor_applicant(client)
    body = {"status": "approved"}
    if commission is not None:
        body["commission_pct"] = commission
    assert client.patch(f"{API}/admin/vendors/{vp['id']}", headers=admin, json=body).status_code == 200
    return h, vp


def new_theater(client, h, admin=None, approve=True):
    city = client.get(f"{API}/cities").json()[0]
    r = client.post(f"{API}/vendor/theaters", headers=h, json={"name": f"Cine {uuid.uuid4().hex[:5]}", "city_id": city["id"], "address": "1 Main Road"})
    assert r.status_code == 201, r.text
    t = r.json()
    if approve:
        assert client.patch(f"{API}/admin/theaters/{t['id']}/review", headers=admin, json={"status": "approved"}).status_code == 200
    return t


def live_theater(client, admin, commission=None):
    """vendor -> approved theater -> screen -> one show tomorrow+2. Returns (headers, vendor, theater, screen, show_id)."""
    h, vp = approved_vendor(client, admin, commission)
    t = new_theater(client, h, admin)
    s = client.post(f"{API}/vendor/theaters/{t['id']}/screens", headers=h, json={"name": "Screen 1", "layout": LAYOUT})
    assert s.status_code == 201, s.text
    show_id = schedule(client, h, s.json()["id"])
    return h, vp, t, s.json(), show_id


def schedule(client, h, screen_id, day_offset=3):
    movie = client.get(f"{API}/movies", params={"status": "now_showing"}).json()
    lang = client.get(f"{API}/languages").json()[0]
    # now_showing requires public shows; fall back to any movie from the admin list
    mid = movie["items"][0]["id"] if movie["items"] else client.get(f"{API}/movies").json()["items"][0]["id"]
    day = (datetime.now(timezone.utc) + timedelta(days=day_offset)).date().isoformat()
    r = client.post(f"{API}/vendor/shows/bulk", headers=h, json={
        "movie_id": mid, "screen_id": screen_id, "language_id": lang["id"], "dates": [day], "times": ["12:00"], "prices": PRICES})
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 1, r.json()
    shows = client.get(f"{API}/vendor/shows", headers=h, params={"screen_id": screen_id}).json()["items"]
    return shows[0]["id"]


def test_unapproved_vendor_cannot_list_anything(client, admin):
    h, u, vp = vendor_applicant(client)
    assert vp["status"] == "pending"
    assert client.get(f"{API}/users/me", headers=h).json()["role"] == "user"
    assert client.get(f"{API}/vendor/theaters", headers=h).status_code == 403  # not a vendor yet
    assert client.post(f"{API}/vendor/register", headers=h, json={"business_name": "Again Ltd", "contact_phone": "+919999900000"}).status_code == 409
    # rejection requires a reason, then the applicant stays a customer
    assert client.patch(f"{API}/admin/vendors/{vp['id']}", headers=admin, json={"status": "rejected"}).status_code == 400
    assert client.patch(f"{API}/admin/vendors/{vp['id']}", headers=admin, json={"status": "rejected", "reason": "GST mismatch"}).status_code == 200
    assert client.get(f"{API}/users/me", headers=h).json()["role"] == "user"
    assert client.get(f"{API}/vendor/profile", headers=h).json()["rejection_reason"] == "GST mismatch"


def test_approval_workflow_and_public_visibility(client, admin):
    h, vp = approved_vendor(client, admin)
    assert client.get(f"{API}/users/me", headers=h).json()["role"] == "vendor"
    t = new_theater(client, h, approve=False)
    assert t["approval_status"] == "pending"
    # pending theater is invisible to customers (list, detail, search)
    assert client.get(f"{API}/venues/{t['id']}").status_code == 404
    assert t["id"] not in [v["id"] for v in client.get(f"{API}/venues", params={"size": 100, "city_id": t["city_id"]}).json()["items"]]
    # screens/shows only after approval
    r = client.post(f"{API}/vendor/theaters/{t['id']}/screens", headers=h, json={"name": "S1", "layout": LAYOUT})
    assert r.status_code == 409 and r.json()["error"]["code"] == "theater_not_approved"
    # admin rejects (reason mandatory), vendor fixes and resubmits, admin approves
    assert client.patch(f"{API}/admin/theaters/{t['id']}/review", headers=admin, json={"status": "rejected"}).status_code == 400
    client.patch(f"{API}/admin/theaters/{t['id']}/review", headers=admin, json={"status": "rejected", "reason": "Address unclear"})
    mine = [x for x in client.get(f"{API}/vendor/theaters", headers=h).json() if x["id"] == t["id"]][0]
    assert mine["approval_status"] == "rejected" and mine["rejection_reason"] == "Address unclear"
    assert client.post(f"{API}/vendor/theaters/{t['id']}/resubmit", headers=h).json()["approval_status"] == "pending"
    client.patch(f"{API}/admin/theaters/{t['id']}/review", headers=admin, json={"status": "approved"})
    assert client.get(f"{API}/venues/{t['id']}").status_code == 200


def test_suspended_vendor_disappears_and_cannot_be_booked(client, admin, user):
    h, vp, t, scr, show_id = live_theater(client, admin)
    cust, _ = user
    assert client.get(f"{API}/shows/{show_id}").status_code == 200
    client.patch(f"{API}/admin/vendors/{vp['id']}", headers=admin, json={"status": "suspended", "reason": "Policy breach"})
    assert client.get(f"{API}/shows/{show_id}").status_code == 404
    assert client.get(f"{API}/venues/{t['id']}").status_code == 404
    seat = [s for s in client.get(f"{API}/vendor/shows/{show_id}/seats", headers=h).json()["seats"]][0]
    assert client.put(f"{API}/shows/{show_id}/locks", headers=cust, json={"seat_ids": [seat["id"]]}).status_code in (404, 409)
    assert client.post(f"{API}/vendor/theaters", headers=h, json={"name": "New", "city_id": t["city_id"], "address": "x y z"}).status_code == 403
    client.patch(f"{API}/admin/vendors/{vp['id']}", headers=admin, json={"status": "approved"})
    assert client.get(f"{API}/shows/{show_id}").status_code == 200


def test_booking_commission_blocked_seats_and_vendor_scoping(client, admin, user):
    h, vp, t, scr, show_id = live_theater(client, admin, commission=20)
    cust, _ = user
    # maintenance: block one seat on the screen -> unavailable to customers
    seats = client.get(f"{API}/vendor/screens/{scr['id']}/seats", headers=h).json()
    a1 = [s for s in seats if s["row"] == "A" and s["number"] == 1][0]
    assert client.post(f"{API}/vendor/screens/{scr['id']}/seats/block", headers=h, json={"seat_ids": [a1["id"]], "reason": "Broken recliner"}).status_code == 200
    public = {f"{s['row']}{s['number']}": s for s in client.get(f"{API}/shows/{show_id}").json()["seats"]}
    assert public["A1"]["status"] == "blocked"
    assert client.put(f"{API}/shows/{show_id}/locks", headers=cust, json={"seat_ids": [public["A1"]["id"]]}).status_code == 409
    # book A2 + A3
    ids = [public["A2"]["id"], public["A3"]["id"]]
    assert client.put(f"{API}/shows/{show_id}/locks", headers=cust, json={"seat_ids": ids}).status_code == 200
    co = client.post(f"{API}/bookings", headers=cust, json={"kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show_id, "seat_ids": ids}).json()
    r, _ = pay(client, cust, co)
    assert r.status_code == 200
    # 2 x Gold 300 = 600 net; 20% commission = 120; vendor share = 480
    vb = client.get(f"{API}/vendor/bookings", headers=h).json()["items"]
    assert len(vb) == 1 and vb[0]["commission_paise"] == 12000 and vb[0]["vendor_share_paise"] == 48000
    e = client.get(f"{API}/vendor/earnings", headers=h).json()
    assert e["gross_paise"] == 60000 and e["commission_paise"] == 12000 and e["net_paise"] == 48000 and e["available_paise"] == 0  # show not started
    occ = client.get(f"{API}/vendor/shows", headers=h).json()["items"][0]
    assert occ["booked"] == 2 and occ["blocked"] == 1 and occ["total"] == 6

    # another approved vendor sees nothing of this and cannot touch it (404, never 403)
    h2, vp2 = approved_vendor(client, admin)
    assert client.get(f"{API}/vendor/bookings", headers=h2).json()["total"] == 0
    assert client.get(f"{API}/vendor/shows", headers=h2).json()["total"] == 0
    assert client.get(f"{API}/vendor/earnings", headers=h2).json()["gross_paise"] == 0
    for method, path, body in [
        ("get", f"/vendor/theaters/{t['id']}/screens", None), ("get", f"/vendor/screens/{scr['id']}/seats", None),
        ("post", f"/vendor/screens/{scr['id']}/seats/block", {"seat_ids": [a1["id"]]}), ("get", f"/vendor/shows/{show_id}/seats", None),
        ("post", f"/vendor/shows/{show_id}/cancel", None), ("patch", f"/vendor/shows/{show_id}/prices", {"prices": PRICES}),
        ("post", f"/vendor/bookings/{co['booking']['id']}/cancel", None), ("patch", f"/vendor/theaters/{t['id']}", {"name": "Hijack", "city_id": t["city_id"], "address": "1 Main Road"}),
        ("delete", f"/vendor/theaters/{t['id']}", None), ("put", f"/vendor/screens/{scr['id']}", {"name": "S", "layout": LAYOUT}),
    ]:
        r = getattr(client, method)(f"{API}{path}", headers=h2, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, path, r.status_code, r.text)
    # customers/organizers can't use the portal at all
    assert client.get(f"{API}/vendor/shows", headers=cust).status_code == 403
    assert client.get(f"{API}/vendor/earnings").status_code == 401

    # vendor cancels the booking -> customer refunded, seats freed, earnings drop
    r = client.post(f"{API}/vendor/bookings/{vb[0]['id']}/cancel", headers=h, json={"reason": "Projector failure"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["refund_paise"] == 60000
    assert client.get(f"{API}/vendor/earnings", headers=h).json()["net_paise"] == 0


def test_price_update_only_affects_unsold_seats(client, admin, user):
    h, vp, t, scr, show_id = live_theater(client, admin)
    cust, _ = user
    pub = {f"{s['row']}{s['number']}": s for s in client.get(f"{API}/shows/{show_id}").json()["seats"]}
    ids = [pub["A1"]["id"]]
    client.put(f"{API}/shows/{show_id}/locks", headers=cust, json={"seat_ids": ids})
    co = client.post(f"{API}/bookings", headers=cust, json={"kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show_id, "seat_ids": ids}).json()
    pay(client, cust, co)
    assert client.patch(f"{API}/vendor/shows/{show_id}/prices", headers=h, json={"prices": {"Gold": 50000}}).status_code == 400
    assert client.patch(f"{API}/vendor/shows/{show_id}/prices", headers=h, json={"prices": {"Gold": 50000, "Silver": 25000}}).status_code == 200
    after = {f"{s['row']}{s['number']}": s for s in client.get(f"{API}/shows/{show_id}").json()["seats"]}
    assert after["A1"]["price_paise"] == 30000 and after["A2"]["price_paise"] == 50000 and after["B1"]["price_paise"] == 25000


def test_show_moderation_setting(client, admin):
    h, vp = approved_vendor(client, admin)
    t = new_theater(client, h, admin)
    scr = client.post(f"{API}/vendor/theaters/{t['id']}/screens", headers=h, json={"name": "S1", "layout": LAYOUT}).json()
    assert client.put(f"{API}/admin/settings", headers=admin, json={"require_show_approval": True}).json()["require_show_approval"] is True
    try:
        show_id = schedule(client, h, scr["id"])
        assert client.get(f"{API}/shows/{show_id}").status_code == 404  # unreviewed => hidden
        pend = client.get(f"{API}/admin/shows/pending", headers=admin).json()
        assert any(show_id in g["show_ids"] for g in pend)
        assert client.post(f"{API}/admin/shows/review", headers=admin, json={"show_ids": [show_id], "status": "approved"}).status_code == 200
        assert client.get(f"{API}/shows/{show_id}").status_code == 200
    finally:
        client.put(f"{API}/admin/settings", headers=admin, json={"require_show_approval": False})


def test_payouts_flow(client, admin, user):
    h, vp, t, scr, show_id = live_theater(client, admin, commission=10)
    cust, _ = user
    pub = {f"{s['row']}{s['number']}": s for s in client.get(f"{API}/shows/{show_id}").json()["seats"]}
    ids = [pub["A1"]["id"], pub["A2"]["id"], pub["A3"]["id"]]  # 3 x 300 = 900, share 810
    client.put(f"{API}/shows/{show_id}/locks", headers=cust, json={"seat_ids": ids})
    co = client.post(f"{API}/bookings", headers=cust, json={"kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show_id, "seat_ids": ids}).json()
    pay(client, cust, co)
    r = client.post(f"{API}/vendor/payouts", headers=h, json={})
    assert r.status_code == 400  # earnings are only withdrawable once the show has started
    with SessionLocal() as db:  # the show happened yesterday
        s = db.get(Show, show_id)
        s.starts_at, s.ends_at = datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc) - timedelta(hours=20)
        db.commit()
    e = client.get(f"{API}/vendor/earnings", headers=h).json()
    assert e["available_paise"] == 81000
    assert client.post(f"{API}/vendor/payouts", headers=h, json={"amount_paise": 90000}).status_code == 400  # more than available
    p = client.post(f"{API}/vendor/payouts", headers=h, json={"amount_paise": 50000})
    assert p.status_code == 201 and p.json()["status"] == "requested"
    assert client.get(f"{API}/vendor/earnings", headers=h).json()["available_paise"] == 31000
    # admin must give a bank reference to mark paid; processed once only
    pid = p.json()["id"]
    assert client.patch(f"{API}/admin/payouts/{pid}", headers=admin, json={"status": "paid"}).status_code == 400
    assert client.patch(f"{API}/admin/payouts/{pid}", headers=admin, json={"status": "paid", "reference": "UTR123456"}).json()["status"] == "paid"
    assert client.patch(f"{API}/admin/payouts/{pid}", headers=admin, json={"status": "rejected"}).status_code == 409
    e = client.get(f"{API}/vendor/earnings", headers=h).json()
    assert e["paid_out_paise"] == 50000 and e["available_paise"] == 31000
    # vendors cannot process payouts
    assert client.patch(f"{API}/admin/payouts/{pid}", headers=h, json={"status": "paid", "reference": "x"}).status_code == 403
    com = client.get(f"{API}/admin/commissions", headers=admin).json()
    row = [v for v in com["vendors"] if v["vendor_id"] == vp["id"]][0]
    assert row["commission_paise"] == 9000 and row["paid_out_paise"] == 50000


def test_movie_request_flow(client, admin):
    h, vp = approved_vendor(client, admin)
    r = client.post(f"{API}/vendor/movie-requests", headers=h, json={"title": f"Requested {uuid.uuid4().hex[:4]}", "duration_min": 111, "release_date": "2026-12-25"})
    assert r.status_code == 201
    rid = r.json()["id"]
    res = client.patch(f"{API}/admin/movie-requests/{rid}", headers=admin, json={"status": "approved"})
    assert res.status_code == 200 and res.json()["movie_id"]
    assert client.get(f"{API}/movies/{res.json()['movie_id']}").status_code == 200
    assert client.patch(f"{API}/admin/movie-requests/{rid}", headers=admin, json={"status": "rejected"}).status_code == 409


def test_audit_trail_and_csv_export(client, admin):
    h, vp, t, scr, show_id = live_theater(client, admin)
    logs = client.get(f"{API}/admin/audit-logs", headers=admin, params={"size": 100}).json()["items"]
    actions = {(l["action"], l["entity_type"]) for l in logs}
    for expected in [("vendor.approved", "vendor"), ("theater.submit", "theater"), ("theater.approved", "theater"), ("screen.create", "screen"), ("show.bulk_create", "screen")]:
        assert expected in actions, expected
    entry = [l for l in logs if l["action"] == "vendor.approved" and l["entity_id"] == str(vp["id"])][0]
    assert entry["actor_role"] == "admin" and entry["actor_email"] == "admin@test.example.com"
    assert client.get(f"{API}/admin/audit-logs", headers=h).status_code == 403
    r = client.get(f"{API}/vendor/reports/sales", headers=h, params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and r.text.startswith("booked_at,booking_id")
    assert client.get(f"{API}/admin/reports/marketplace", headers=admin).json()["approvals"]["vendors_pending"] >= 0
    assert client.get(f"{API}/admin/reports/bookings.csv", headers=admin).status_code == 200
    assert client.get(f"{API}/admin/reports/bookings.csv", headers=h).status_code == 403


def test_vendor_layout_editable_with_shows_when_no_seat_is_sold(client, admin):
    h, vp, t, scr, show_id = live_theater(client, admin)
    new_layout = {"rows": [{"label": "A", "category": "Gold", "seats": 5, "aisles": []}, {"label": "B", "category": "Silver", "seats": 3, "aisles": []}]}
    r = client.put(f"{API}/vendor/screens/{scr['id']}", headers=h, json={"name": "Screen 1", "layout": new_layout})
    assert r.status_code == 200
    # bad price keys are rejected
    day = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    lang = client.get(f"{API}/languages").json()[0]
    mid = client.get(f"{API}/movies").json()["items"][0]["id"]
    bad = client.post(f"{API}/vendor/shows/bulk", headers=h, json={"movie_id": mid, "screen_id": scr["id"], "language_id": lang["id"], "dates": [day], "times": ["12:00"], "prices": {"Gold": 100}})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "prices_mismatch"
