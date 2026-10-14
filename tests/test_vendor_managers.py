"""Vendor-created theater managers: admin approval, theater scoping and what they must never reach."""
from tests.conftest import login
from tests.test_vendor_workflow import LAYOUT, PRICES, approved_vendor, live_theater, new_theater, schedule

API = "/api/v1"
PW = "Manager@12345"


def make_manager(client, vh, theater_ids, email, name="Mia Manager"):
    r = client.post(f"{API}/vendor/staff", headers=vh, json={"name": name, "email": email, "password": PW, "theater_ids": theater_ids})
    assert r.status_code == 201, r.text
    return r.json()


def approve(client, admin, staff_id):
    r = client.patch(f"{API}/admin/vendor-staff/{staff_id}", headers=admin, json={"status": "approved"})
    assert r.status_code == 200, r.text


def two_theaters(client, admin):
    """One vendor with theater A (screen + show) and theater B (screen + show)."""
    vh, _vp, ta, sa, show_a = live_theater(client, admin)
    tb = new_theater(client, vh, admin)
    sb = client.post(f"{API}/vendor/theaters/{tb['id']}/screens", headers=vh, json={"name": "Screen B", "layout": LAYOUT}).json()
    show_b = schedule(client, vh, sb["id"], day_offset=4)
    return vh, ta, sa, show_a, tb, sb, show_b


def test_new_manager_cannot_sign_in_until_admin_approves(client, admin):
    vh, ta, *_ = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-pending@test.example.com")
    assert m["status"] == "pending"
    r = client.post(f"{API}/auth/login", json={"email": "mgr-pending@test.example.com", "password": PW})
    assert r.status_code == 403 and r.json()["error"]["code"] == "staff_pending"
    # rejection needs a reason, and a rejected account stays locked out
    assert client.patch(f"{API}/admin/vendor-staff/{m['id']}", headers=admin, json={"status": "rejected"}).status_code == 400
    assert client.patch(f"{API}/admin/vendor-staff/{m['id']}", headers=admin, json={"status": "rejected", "reason": "Unknown person"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "mgr-pending@test.example.com", "password": PW}).status_code == 403
    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=vh, json={"disabled": False}).status_code == 409  # vendor cannot self-approve
    assert client.patch(f"{API}/admin/vendor-staff/{m['id']}", headers=admin, json={"status": "approved"}).status_code == 409  # already reviewed


def test_only_an_admin_can_approve_and_only_an_approved_vendor_can_create(client, admin, user):
    vh, ta, *_ = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-self@test.example.com")
    assert client.patch(f"{API}/admin/vendor-staff/{m['id']}", headers=vh, json={"status": "approved"}).status_code == 403
    assert client.get(f"{API}/admin/vendor-staff", headers=vh).status_code == 403
    assert client.post(f"{API}/vendor/staff", headers=user[0], json={"name": "X Y", "email": "x@test.example.com", "password": PW, "theater_ids": [ta["id"]]}).status_code == 403
    listed = client.get(f"{API}/admin/vendor-staff", headers=admin, params={"status": "pending"}).json()["items"]
    assert any(i["id"] == m["id"] and i["vendor"] for i in listed)


def test_manager_is_limited_to_assigned_theaters(client, admin):
    vh, ta, sa, show_a, tb, sb, show_b = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-scope@test.example.com")
    approve(client, admin, m["id"])
    mh = login(client, "mgr-scope@test.example.com", PW)

    me = client.get(f"{API}/vendor/me", headers=mh).json()
    assert me["role"] == "manager" and [t["id"] for t in me["theaters"]] == [ta["id"]]
    assert [t["id"] for t in client.get(f"{API}/vendor/theaters", headers=mh).json()] == [ta["id"]]
    assert client.get(f"{API}/vendor/theaters/{ta['id']}/screens", headers=mh).status_code == 200
    assert client.get(f"{API}/vendor/theaters/{tb['id']}/screens", headers=mh).status_code == 404

    shows = client.get(f"{API}/vendor/shows", headers=mh).json()["items"]
    assert {s["id"] for s in shows} == {show_a} and all(s["revenue_paise"] == 0 for s in shows)

    # allowed: price change, per-show seat blocking, scheduling on the assigned screen
    assert client.patch(f"{API}/vendor/shows/{show_a}/prices", headers=mh, json={"prices": {"Gold": 35000, "Silver": 21000}}).status_code == 200
    seat = client.get(f"{API}/vendor/shows/{show_a}/seats", headers=mh).json()["seats"][0]["id"]
    assert client.post(f"{API}/vendor/shows/{show_a}/seats/block", headers=mh, json={"show_seat_ids": [seat], "blocked": True}).status_code == 200
    assert schedule(client, mh, sa["id"], day_offset=6)

    # every resource of the other theater answers 404, never 403
    assert client.patch(f"{API}/vendor/shows/{show_b}/prices", headers=mh, json={"prices": PRICES}).status_code == 404
    assert client.get(f"{API}/vendor/shows/{show_b}/seats", headers=mh).status_code == 404
    assert client.post(f"{API}/vendor/shows/bulk", headers=mh, json={
        "movie_id": 1, "screen_id": sb["id"], "language_id": 1, "dates": ["2030-01-01"], "times": ["10:00"], "prices": PRICES}).status_code == 404
    assert client.post(f"{API}/vendor/screens/{sb['id']}/seats/block", headers=mh, json={"seat_ids": [1], "blocked": True}).status_code == 404


def test_manager_cannot_reach_money_bookings_or_staff_endpoints(client, admin):
    vh, ta, sa, show_a, *_ = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-money@test.example.com")
    approve(client, admin, m["id"])
    mh = login(client, "mgr-money@test.example.com", PW)
    for method, path, body in [
        ("get", "/vendor/earnings", None), ("get", "/vendor/payouts", None), ("post", "/vendor/payouts", {"amount_paise": 100}),
        ("get", "/vendor/bookings", None), ("get", "/vendor/analytics", None), ("get", "/vendor/reports/sales", None),
        ("get", "/vendor/staff", None), ("post", f"/vendor/shows/{show_a}/cancel", {}),
        ("post", "/vendor/theaters", {"name": "Sneaky", "city_id": 1, "address": "x"}),
        ("post", "/vendor/staff", {"name": "Eve Evil", "email": "eve@test.example.com", "password": PW, "theater_ids": [ta["id"]]}),
        ("get", "/admin/users", None), ("get", "/helpdesk/tickets", None), ("get", "/organizer/events", None),
    ]:
        r = getattr(client, method)(f"{API}{path}", headers=mh, **({"json": body} if body is not None else {}))
        assert r.status_code in (403, 422), (path, r.status_code)


def test_vendor_can_edit_theaters_disable_and_reenable(client, admin):
    vh, ta, sa, show_a, tb, sb, show_b = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-edit@test.example.com")
    approve(client, admin, m["id"])
    mh = login(client, "mgr-edit@test.example.com", PW)
    assert client.get(f"{API}/vendor/shows/{show_b}/seats", headers=mh).status_code == 404

    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=vh, json={"theater_ids": [ta["id"], tb["id"]]}).json()["theater_ids"] == sorted([ta["id"], tb["id"]])
    assert client.get(f"{API}/vendor/shows/{show_b}/seats", headers=mh).status_code == 200

    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=vh, json={"disabled": True}).json()["status"] == "disabled"
    assert client.get(f"{API}/vendor/theaters", headers=mh).status_code == 401  # existing token stops working at once
    assert client.post(f"{API}/auth/login", json={"email": "mgr-edit@test.example.com", "password": PW}).status_code == 403
    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=vh, json={"disabled": False}).json()["status"] == "active"
    assert client.get(f"{API}/vendor/theaters", headers=mh).status_code == 200


def test_vendors_cannot_touch_each_others_staff_or_assign_foreign_theaters(client, admin):
    vh, ta, *_ = two_theaters(client, admin)
    other_h, _ = approved_vendor(client, admin)
    other_t = new_theater(client, other_h, admin)
    assert client.post(f"{API}/vendor/staff", headers=vh, json={"name": "Foreign Kid", "email": "foreign@test.example.com", "password": PW,
                                                                "theater_ids": [ta["id"], other_t["id"]]}).status_code == 404
    m = make_manager(client, vh, [ta["id"]], "mgr-mine@test.example.com")
    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=other_h, json={"disabled": True}).status_code == 404
    assert client.patch(f"{API}/vendor/staff/{m['id']}", headers=other_h, json={"theater_ids": [other_t["id"]]}).status_code == 404
    assert client.get(f"{API}/vendor/staff", headers=other_h).json() == []
    assert client.post(f"{API}/vendor/staff", headers=vh, json={"name": "Dup Mgr", "email": "MGR-MINE@test.example.com", "password": PW, "theater_ids": [ta["id"]]}).status_code == 409


def test_manager_stops_working_if_the_vendor_is_suspended(client, admin):
    vh, ta, *_ = two_theaters(client, admin)
    m = make_manager(client, vh, [ta["id"]], "mgr-susp@test.example.com")
    approve(client, admin, m["id"])
    mh = login(client, "mgr-susp@test.example.com", PW)
    vendor_id = client.get(f"{API}/vendor/profile", headers=vh).json()["id"]
    assert client.patch(f"{API}/admin/vendors/{vendor_id}", headers=admin, json={"status": "suspended", "reason": "Policy"}).status_code == 200
    assert client.get(f"{API}/vendor/me", headers=mh).status_code == 200  # read-only identity still resolves
    assert client.patch(f"{API}/vendor/shows/1/prices", headers=mh, json={"prices": PRICES}).status_code == 403
