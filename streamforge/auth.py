"""Stateless JWT authentication."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import Blueprint, current_app, g, jsonify, request

from .errors import APIError
from .extensions import db, limiter
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user.id, "iat": now, "exp": now + current_app.config["JWT_TTL"]}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _user_from_request() -> User | None:
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    if not token:
        return None
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, "token_expired", "Session expired, please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(401, "invalid_token", "Invalid authentication token.") from exc
    user = db.session.get(User, payload["sub"])
    if user is None:
        raise APIError(401, "invalid_token", "User no longer exists.")
    return user


def optional_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        return fn(*args, **kwargs)

    return wrapper


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        if g.user is None:
            raise APIError(401, "auth_required", "Log in to do that.")
        return fn(*args, **kwargs)

    return wrapper


def _json() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "invalid_json", "Request body must be a JSON object.")
    return data


@bp.post("/register")
@limiter.limit("10/minute; 50/day")
def register():
    data = _json()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    name = str(data.get("display_name", "")).strip() or email.split("@")[0]
    if not EMAIL_RE.match(email):
        raise APIError(422, "invalid_email", "Enter a valid email address.")
    if len(password) < 8:
        raise APIError(422, "weak_password", "Password must be at least 8 characters.")
    if db.session.query(User.id).filter_by(email=email).first():
        raise APIError(409, "email_taken", "An account with that email already exists.")
    user = User(email=email, display_name=name[:80])
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"user": user.to_dict(), "token": issue_token(user)}), 201


@bp.post("/login")
@limiter.limit("10/minute")
def login():
    data = _json()
    email = str(data.get("email", "")).strip().lower()
    user = db.session.query(User).filter_by(email=email).first()
    if user is None or not user.check_password(str(data.get("password", ""))):
        raise APIError(401, "invalid_credentials", "Wrong email or password.")
    return jsonify({"user": user.to_dict(), "token": issue_token(user)})


@bp.get("/me")
@require_auth
def me():
    return jsonify({"user": g.user.to_dict()})
