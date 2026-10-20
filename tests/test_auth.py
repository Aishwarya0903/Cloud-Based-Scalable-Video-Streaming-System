def test_register_login_me(client):
    r = client.post(
        "/api/v1/auth/register", json={"email": "Bob@Example.com", "password": "password123"}
    )
    assert r.status_code == 201
    assert r.get_json()["user"]["email"] == "bob@example.com"

    r = client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "password123"})
    assert r.status_code == 200
    token = r.get_json()["token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.get_json()["user"]["display_name"] == "bob"


def test_register_validation(client):
    assert client.post("/api/v1/auth/register", json={"email": "nope", "password": "x" * 8}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 422
    client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "longenough"})
    r = client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "longenough"})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "email_taken"


def test_bad_credentials_and_tokens(client, token):
    r = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.get_json()["error"]["code"] == "invalid_token"


def test_health(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.get_json()["checks"] == {"database": "ok", "storage": "ok"}


def test_unknown_api_route_is_json(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"
