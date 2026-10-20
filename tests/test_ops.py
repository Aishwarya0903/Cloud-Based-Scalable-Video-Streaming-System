from moto import mock_aws

from streamforge import create_app
from streamforge.extensions import db


def test_metrics_exposes_http_and_pipeline_series(client):
    client.get("/api/v1/videos")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'streamforge_http_requests_total{method="GET",route="/api/v1/videos",status="200"}' in body
    assert "streamforge_http_request_seconds_bucket" in body
    assert 'streamforge_videos{status="ready"}' in body
    assert "streamforge_qoe_startup_seconds_bucket" in body


def test_request_id_is_generated_or_propagated(client):
    r = client.get("/healthz")
    assert len(r.headers["X-Request-ID"]) == 32
    r = client.get("/healthz", headers={"X-Request-ID": "edge-abc123"})
    assert r.headers["X-Request-ID"] == "edge-abc123"


def test_login_is_rate_limited():
    with mock_aws():
        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "S3_ENDPOINT_URL": None,
                          "RATELIMIT_ENABLED": True, "RATELIMIT_STORAGE_URI": "memory://",
                          "SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes"})
        client = app.test_client()
        with app.app_context():
            codes = [client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "nope"}).status_code
                     for _ in range(11)]
            assert codes[:10] == [401] * 10 and codes[10] == 429
            r = client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "nope"})
            assert r.get_json()["error"]["code"] == "too_many_requests"
            assert "Retry-After" in r.headers
            db.session.remove()
