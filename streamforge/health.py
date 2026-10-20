from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from .extensions import db
from .storage import get_storage

bp = Blueprint("health", __name__)


@bp.get("/healthz")
def liveness():
    """Process is up. Cheap - used by container restart policies."""
    return jsonify({"status": "ok"})


@bp.get("/readyz")
def readiness():
    """Dependencies reachable. Load balancers should only route here when 200."""
    checks: dict[str, str] = {}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure
        checks["database"] = f"error: {exc.__class__.__name__}"
    try:
        get_storage().ping()
        checks["storage"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = f"error: {exc.__class__.__name__}"
    healthy = all(v == "ok" for v in checks.values())
    return jsonify({"status": "ok" if healthy else "degraded", "checks": checks}), (
        200 if healthy else 503
    )
