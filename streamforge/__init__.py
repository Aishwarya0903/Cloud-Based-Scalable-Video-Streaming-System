"""StreamForge - a cloud-native adaptive video streaming platform."""

from __future__ import annotations

import logging

from flask import Flask

from .config import load_config
from .errors import register_error_handlers
from .extensions import db
from .storage import S3Storage

__version__ = "1.0.0"


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(load_config())
    if overrides:
        app.config.update(overrides)
    if app.config["ENV"] == "production" and app.config["SECRET_KEY"].startswith("dev-only"):
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    db.init_app(app)
    app.extensions["storage"] = S3Storage(app.config)

    from . import auth, health
    from .api import uploads, videos

    for blueprint in (health.bp, auth.bp, uploads.bp, videos.bp):
        app.register_blueprint(blueprint)
    register_error_handlers(app)

    with app.app_context():
        db.create_all()
        if app.config["S3_CREATE_BUCKETS"]:
            app.extensions["storage"].ensure_buckets()
        # Don't hand pooled connections to forked gunicorn workers (--preload).
        # (In-memory SQLite lives in its single connection, so keep that one.)
        if db.engine.url.get_backend_name() != "sqlite":
            db.engine.dispose()

    return app
