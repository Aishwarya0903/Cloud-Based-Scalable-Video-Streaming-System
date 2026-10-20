"""Prometheus metrics, request IDs and structured logs.

Gunicorn runs several worker processes, each with its own memory, so when
PROMETHEUS_MULTIPROC_DIR is set, metrics are written to shared files and merged at
scrape time; otherwise the normal in-process registry is used (dev, tests).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import timedelta

from flask import Blueprint, Flask, Response, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily

bp = Blueprint("metrics", __name__)

HTTP_REQUESTS = Counter("streamforge_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "streamforge_http_request_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
UPLOADS_COMPLETED = Counter("streamforge_uploads_completed_total", "Multipart uploads completed")
UPLOAD_BYTES = Counter("streamforge_upload_bytes_total", "Bytes received through completed uploads")
VIEWS = Counter("streamforge_views_total", "Playback sessions started")
QOE_STARTUP = Histogram(
    "streamforge_qoe_startup_seconds", "Time from page load to first frame, reported by players",
    buckets=(0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10),
)
QOE_REBUFFER = Histogram(
    "streamforge_qoe_rebuffer_ratio", "Share of each heartbeat interval spent stalled",
    buckets=(0, 0.001, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1),
)


class PipelineCollector:
    """State read from the database / queue at scrape time (always current, any process)."""

    def __init__(self, app: Flask):
        self.app = app

    def collect(self):
        from .extensions import db
        from .jobs import queue_depth
        from .models import Video, VideoStatus, utcnow

        with self.app.app_context():
            by_status = GaugeMetricFamily("streamforge_videos", "Videos by pipeline status", labels=["status"])
            counts = dict(db.session.query(Video.status, db.func.count()).group_by(Video.status).all())
            for status in VideoStatus.ALL:
                by_status.add_metric([status], counts.get(status, 0))
            yield by_status

            depth = queue_depth()
            if depth is not None:
                yield GaugeMetricFamily("streamforge_queue_depth", "Transcode jobs waiting", value=depth)

            recent = db.session.query(db.func.avg(Video.processing_seconds), db.func.count()).filter(
                Video.ready_at >= utcnow() - timedelta(hours=1)).one()
            yield GaugeMetricFamily("streamforge_transcode_seconds_avg_1h",
                                    "Mean transcode time of videos finished in the last hour",
                                    value=float(recent[0] or 0))
            yield GaugeMetricFamily("streamforge_transcodes_1h", "Videos finished in the last hour",
                                    value=recent[1])
            db.session.remove()


@bp.get("/metrics")
def metrics():
    from flask import current_app

    registry = CollectorRegistry()
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY as registry  # noqa: N811
    output = generate_latest(registry)
    output += generate_latest(_pipeline_registry(current_app))
    return Response(output, mimetype=CONTENT_TYPE_LATEST)


def _pipeline_registry(app: Flask) -> CollectorRegistry:
    reg = app.extensions.get("pipeline_registry")
    if reg is None:
        reg = CollectorRegistry()
        reg.register(PipelineCollector(app))
        app.extensions["pipeline_registry"] = reg
    return reg


# ------------------------------------------------------- request id + logging
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "ms", "user"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def init_app(app: Flask) -> None:
    if os.getenv("LOG_FORMAT", "text") == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.root.handlers = [handler]
    access = logging.getLogger("streamforge.access")

    @app.before_request
    def _start():
        g.start = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex

    @app.after_request
    def _finish(response):
        route = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - g.get("start", time.perf_counter())
        if route not in ("/metrics", "/healthz"):
            HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            if request.path.startswith("/api/"):
                user = g.get("user")
                access.info("%s %s %s", request.method, request.path, response.status_code, extra={
                    "request_id": g.get("request_id"), "method": request.method, "path": request.path,
                    "status": response.status_code, "ms": round(elapsed * 1000, 1),
                    "user": user.id if user else None,
                })
        response.headers["X-Request-ID"] = g.get("request_id", "")
        return response
