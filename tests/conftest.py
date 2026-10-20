import os

import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from streamforge import create_app  # noqa: E402
from streamforge.extensions import db  # noqa: E402


@pytest.fixture
def app():
    with mock_aws():
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "S3_ENDPOINT_URL": None,
                "S3_PUBLIC_ENDPOINT_URL": None,
                "S3_CREATE_BUCKETS": True,
                "QUEUE_SYNC": True,
                "UPLOAD_PART_SIZE": 5 * 1024 * 1024,
            }
        )
        with app.app_context():
            app.extensions["storage"].ensure_buckets()
            yield app
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def storage(app):
    return app.extensions["storage"]


def _register(client, email="alice@example.com", password="supersecret1", name="Alice"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["token"]


@pytest.fixture
def token(client):
    return _register(client)


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def register(client):
    return lambda **kw: _register(client, **kw)
