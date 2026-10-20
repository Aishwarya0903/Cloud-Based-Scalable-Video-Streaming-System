"""StreamForge - a cloud-native adaptive video streaming platform."""

from __future__ import annotations

import logging

from flask import Flask

from .config import load_config
from .errors import register_error_handlers
from .extensions import db, limiter
from .storage import S3Storage

__version__ = "1.0.0"


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)  # UI assets are served by the web blueprint
    app.config.update(load_config())
    if overrides:
        app.config.update(overrides)
    if app.config["ENV"] == "production" and app.config["SECRET_KEY"].startswith("dev-only"):
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")
    if app.config["ENV"] == "production" and app.config["CDN_SIGNING_SECRET"].startswith("dev-only"):
        raise RuntimeError("Set CDN_SIGNING_SECRET before running in production.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if app.config["TRUSTED_PROXIES"]:
        from werkzeug.middleware.proxy_fix import ProxyFix

        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    db.init_app(app)
    limiter.init_app(app)
    app.extensions["storage"] = S3Storage(app.config)

    from . import auth, cdn, health, metrics
    from .api import analytics, uploads, videos
    from .web import bp as web_bp

    metrics.init_app(app)
    for blueprint in (health.bp, metrics.bp, auth.bp, uploads.bp, videos.bp, analytics.bp, cdn.bp, web_bp):
        app.register_blueprint(blueprint)
    register_error_handlers(app)
    _register_cli(app)

    with app.app_context():
        db.create_all()
        if app.config["S3_CREATE_BUCKETS"]:
            app.extensions["storage"].ensure_buckets()
        # Don't hand pooled connections to forked gunicorn workers (--preload).
        # (In-memory SQLite lives in its single connection, so keep that one.)
        if db.engine.url.get_backend_name() != "sqlite":
            db.engine.dispose()

    return app


def _register_cli(app: Flask) -> None:
    import click

    @app.cli.command("requeue-stuck")
    @click.option("--minutes", default=30, help="Age after which a queued/processing video is stuck.")
    def requeue_stuck(minutes: int) -> None:
        """Re-enqueue videos stuck in queued/processing (e.g. after a worker crash)."""
        from datetime import timedelta

        from .jobs import enqueue_transcode
        from .models import Video, VideoStatus, utcnow

        cutoff = utcnow() - timedelta(minutes=minutes)
        stuck = db.session.query(Video).filter(
            Video.status.in_([VideoStatus.QUEUED, VideoStatus.PROCESSING]), Video.updated_at < cutoff
        ).all()
        for video in stuck:
            enqueue_transcode(video.id)
        click.echo(f"re-enqueued {len(stuck)} video(s)")
