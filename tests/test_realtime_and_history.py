import uuid

from tests.conftest import pay, seat_ids

API = "/api/v1"


def test_websocket_broadcasts_seat_changes(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 1)
    with client.websocket_connect(f"{API}/ws/shows/{show}") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert client.put(f"{API}/shows/{show}/locks", headers=h, json={"seat_ids": ids}).status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "seats" and msg["seats"] == [{"id": ids[0], "status": "locked"}]
        client.delete(f"{API}/shows/{show}/locks", headers=h)
        assert ws.receive_json()["seats"] == [{"id": ids[0], "status": "available"}]


def test_private_websocket_requires_valid_token(client, user):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{API}/ws/me?token=garbage") as ws:
            ws.receive_json()


def test_private_websocket_refuses_a_disabled_account_with_a_still_valid_token(client, admin, user):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    h, me = user
    token = h["Authorization"].split()[1]
    with client.websocket_connect(f"{API}/ws/me?token={token}") as ws:  # active: accepted
        ws.send_text("ping")
    assert client.patch(f"{API}/admin/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{API}/ws/me?token={token}") as ws:
            ws.receive_json()


def test_booking_history_scope_is_paginated_in_sql(client, user, show):
    h, _ = user
    ids = seat_ids(client, show, 1)
    client.put(f"{API}/shows/{show}/locks", headers=h, json={"seat_ids": ids})
    co = client.post(f"{API}/bookings", headers=h, json={
        "kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show, "seat_ids": ids}).json()
    assert client.get(f"{API}/bookings", headers=h).json()["total"] == 0  # pending bookings are not history yet
    pay(client, h, co)
    up = client.get(f"{API}/bookings", headers=h, params={"scope": "upcoming"}).json()
    past = client.get(f"{API}/bookings", headers=h, params={"scope": "past"}).json()
    assert up["total"] == 1 and past["total"] == 0


def test_abandon_releases_pending_hold(client, user, user2, show):
    (h1, _), (h2, _) = user, user2
    ids = seat_ids(client, show, 1)
    client.put(f"{API}/shows/{show}/locks", headers=h1, json={"seat_ids": ids})
    co = client.post(f"{API}/bookings", headers=h1, json={
        "kind": "movie", "idempotency_key": uuid.uuid4().hex, "show_id": show, "seat_ids": ids}).json()
    assert client.post(f"{API}/bookings/{co['booking']['id']}/abandon", headers=h2).status_code == 404
    assert client.post(f"{API}/bookings/{co['booking']['id']}/abandon", headers=h1).status_code == 200
    assert client.put(f"{API}/shows/{show}/locks", headers=h2, json={"seat_ids": ids}).status_code == 200
