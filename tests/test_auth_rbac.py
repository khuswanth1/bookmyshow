from tests.conftest import signup


def test_register_login_refresh_me(client):
    h, u = signup(client, "a1@test.example.com")
    assert client.get("/api/v1/users/me", headers=h).json()["email"] == "a1@test.example.com"
    dup = client.post("/api/v1/auth/register", json={"email": "A1@test.example.com", "name": "Dup", "password": "Passw0rdX"})
    assert dup.status_code == 409
    r = client.post("/api/v1/auth/login", json={"email": "a1@test.example.com", "password": "Passw0rdX"})
    assert r.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}).status_code == 200
    # an access token is not accepted as a refresh token
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r.json()["access_token"]}).status_code == 401


def test_bad_credentials_and_validation(client):
    assert client.post("/api/v1/auth/login", json={"email": "nobody@test.example.com", "password": "x"}).status_code == 401
    r = client.post("/api/v1/auth/register", json={"email": "bad", "name": "x", "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    weak = client.post("/api/v1/auth/register", json={"email": "p@test.example.com", "name": "Pat", "password": "onlyletters"})
    assert weak.status_code == 422


def test_google_disabled_without_client_id(client):
    assert client.post("/api/v1/auth/google", json={"credential": "x"}).status_code == 503


def test_role_based_access(client, user, admin, organizer):
    h, _ = user
    assert client.get("/api/v1/bookings").status_code == 401
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403
    assert client.get("/api/v1/admin/users", headers=admin).status_code == 200
    assert client.get("/api/v1/organizer/events", headers=h).status_code == 403
    assert client.get("/api/v1/organizer/events", headers=organizer).status_code == 200
    assert client.get("/api/v1/admin/reports/summary", headers=organizer).status_code == 403
    assert client.get("/api/v1/admin/reports/summary", headers=admin).status_code == 200


def test_organizer_application_review(client, user, admin):
    h, _ = user
    body = {"company_name": "Acme Live", "contact_phone": "+919999999999"}
    r = client.post("/api/v1/organizer/register", headers=h, json=body)
    assert r.status_code == 201
    assert client.post("/api/v1/organizer/register", headers=h, json=body).status_code == 409
    res = client.patch(f"/api/v1/admin/organizers/{r.json()['id']}", headers=admin, json={"status": "approved"})
    assert res.status_code == 200
    assert client.get("/api/v1/users/me", headers=h).json()["role"] == "organizer"
