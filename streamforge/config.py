"""Runtime configuration, read from environment variables (12-factor style).

Every setting has a safe local default so `flask run` works out of the box,
and every setting can be overridden from docker-compose or the cloud runtime.
"""

from __future__ import annotations

import os
from datetime import timedelta

MB = 1024 * 1024
GB = 1024 * MB


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _bool(name: str, default: bool = False) -> bool:
    return str(_env(name, str(default))).lower() in {"1", "true", "yes", "on"}


def load_config() -> dict:
    """Build the config dict at app-creation time (not import time) so tests
    and multiple app instances can each see their own environment."""
    return {
        "ENV": _env("APP_ENV", "development"),
        "SECRET_KEY": _env("SECRET_KEY", "dev-only-insecure-secret-change-me-0123456789"),
        # --- database -------------------------------------------------------
        "SQLALCHEMY_DATABASE_URI": _env("DATABASE_URL", "sqlite:///streamforge.db"),
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        # --- auth -----------------------------------------------------------
        "JWT_TTL": timedelta(hours=_int("JWT_TTL_HOURS", 12)),
        # --- object storage (AWS S3, or any S3-compatible store) ------------
        "AWS_REGION": _env("AWS_REGION", "us-east-1"),
        # Endpoint the API/worker use (e.g. http://minio:9000 inside compose).
        "S3_ENDPOINT_URL": _env("S3_ENDPOINT_URL"),
        # Endpoint embedded in presigned URLs handed to browsers
        # (e.g. http://localhost:9000). Falls back to S3_ENDPOINT_URL.
        "S3_PUBLIC_ENDPOINT_URL": _env("S3_PUBLIC_ENDPOINT_URL"),
        "RAW_BUCKET": _env("RAW_BUCKET", "streamforge-raw"),
        "MEDIA_BUCKET": _env("MEDIA_BUCKET", "streamforge-media"),
        "S3_CREATE_BUCKETS": _bool("S3_CREATE_BUCKETS", False),
        # --- uploads --------------------------------------------------------
        "UPLOAD_PART_SIZE": _int("UPLOAD_PART_SIZE_MB", 8) * MB,
        "MAX_UPLOAD_BYTES": _int("MAX_UPLOAD_GB", 5) * GB,
        "PRESIGN_TTL_SECONDS": _int("PRESIGN_TTL_SECONDS", 3600),
        "ALLOWED_VIDEO_TYPES": {
            "video/mp4",
            "video/quicktime",
            "video/webm",
            "video/x-matroska",
            "video/x-msvideo",
            "video/mpeg",
        },
        # --- delivery / CDN -------------------------------------------------
        "CDN_MODE": _env("CDN_MODE", "direct"),  # direct | edge | cloudfront
        # Prefix for playback URLs: "" = same origin, or https://dxxxx.cloudfront.net
        "CDN_BASE_URL": _env("CDN_BASE_URL", ""),
        "CDN_TOKEN_TTL": _int("CDN_TOKEN_TTL_SECONDS", 4 * 3600),
        "CDN_SIGNING_SECRET": _env("CDN_SIGNING_SECRET", "dev-only-cdn-signing-secret"),
        "CDN_ORIGIN_SECRET": _env("CDN_ORIGIN_SECRET", ""),
        "CLOUDFRONT_KEY_PAIR_ID": _env("CLOUDFRONT_KEY_PAIR_ID", ""),
        "CLOUDFRONT_PRIVATE_KEY": (_env("CLOUDFRONT_PRIVATE_KEY", "") or "").replace("\\n", "\n"),
        # --- queue ----------------------------------------------------------
        "REDIS_URL": _env("REDIS_URL", "redis://localhost:6379/0"),
        "QUEUE_NAME": _env("QUEUE_NAME", "transcode"),
        # Run jobs inline (no Redis) - handy for tests and quick demos.
        "QUEUE_SYNC": _bool("QUEUE_SYNC", False),
    }
