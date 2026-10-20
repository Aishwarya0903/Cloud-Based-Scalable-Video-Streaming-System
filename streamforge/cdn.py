"""Content delivery: signed playback URLs + an origin for the edge cache.

Three modes (CDN_MODE):

  edge        Local CloudFront stand-in. nginx validates a path token with its
              secure_link module, caches responses and fetches misses from this
              app's /origin endpoint (an internal-only custom origin protected by a
              shared header secret - the same pattern used with CloudFront).
  direct      No nginx: Flask validates the same token and streams from S3 itself.
              Handy for `flask run`, tests and tiny deployments.
  cloudfront  Production: CloudFront signed URLs with a custom wildcard policy over
              hls/<video_id>/*. The player appends the same query to every request.

Why a *path* token for edge/direct? HLS playlists reference segments by relative
URL, so a token placed in the directory path is inherited by every segment request
automatically - one signature authorises the whole video, and the cache key can
ignore the token so all viewers share one cached copy.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass

from botocore.exceptions import ClientError
from flask import Blueprint, Response, abort, current_app, request

from .storage import get_storage

bp = Blueprint("cdn", __name__)

SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*\.(m3u8|ts|m4s|jpg|vtt)$")
VIDEO_ID = re.compile(r"^[0-9a-f\-]{36}$")
PASS_HEADERS = ("Content-Type", "Content-Length", "Content-Range", "Cache-Control", "ETag", "Last-Modified")


@dataclass
class Playback:
    hls: str
    poster: str
    thumbnails: str
    query: str  # appended to every request in cloudfront mode; empty otherwise
    expires_at: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# --------------------------------------------------------------------- tokens
def edge_token(video_id: str, expires: int, secret: str) -> str:
    """Matches nginx: secure_link_md5 "$expires$vid $secret" (base64url, no padding)."""
    digest = hashlib.md5(f"{expires}{video_id} {secret}".encode()).digest()  # noqa: S324 - nginx format
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_edge_token(token: str, video_id: str, expires: int, secret: str, now: float | None = None) -> bool:
    if expires < (now or time.time()):
        return False
    return hmac.compare_digest(token, edge_token(video_id, expires, secret))


def _cloudfront_query(resource: str, expires: int) -> str:
    """Signed-URL query for a custom policy (wildcards allowed, unlike canned policies)."""
    from botocore.signers import CloudFrontSigner
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    cfg = current_app.config
    key = serialization.load_pem_private_key(cfg["CLOUDFRONT_PRIVATE_KEY"].encode(), password=None)
    signer = CloudFrontSigner(cfg["CLOUDFRONT_KEY_PAIR_ID"],
                              lambda msg: key.sign(msg, padding.PKCS1v15(), hashes.SHA1()))  # noqa: S303
    policy = json.dumps(
        {"Statement": [{"Resource": resource,
                        "Condition": {"DateLessThan": {"AWS:EpochTime": expires}}}]},
        separators=(",", ":"),
    )
    signed = signer.generate_presigned_url(resource, policy=policy)
    return signed.split("?", 1)[1]


def playback_for(video_id: str, ttl: int | None = None) -> Playback:
    cfg = current_app.config
    expires = int(time.time()) + (ttl or cfg["CDN_TOKEN_TTL"])
    base = cfg["CDN_BASE_URL"].rstrip("/")

    if cfg["CDN_MODE"] == "cloudfront":
        prefix = f"{base}/hls/{video_id}/"
        query = _cloudfront_query(prefix + "*", expires)
        return Playback(f"{prefix}master.m3u8?{query}", f"{prefix}poster.jpg?{query}",
                        f"{prefix}thumbnails.vtt?{query}", query, expires)

    token = edge_token(video_id, expires, cfg["CDN_SIGNING_SECRET"])
    prefix = f"{base}/cdn/{token}/{expires}/{video_id}/"
    return Playback(prefix + "master.m3u8", prefix + "poster.jpg", prefix + "thumbnails.vtt", "", expires)


# --------------------------------------------------------------------- serving
def _stream_from_s3(video_id: str, path: str) -> Response:
    if not VIDEO_ID.match(video_id) or not SAFE_PATH.match(path):
        abort(404)
    storage = get_storage()
    params = {"Bucket": storage.media_bucket, "Key": f"hls/{video_id}/{path}"}
    if request.headers.get("Range"):
        params["Range"] = request.headers["Range"]
    try:
        obj = storage.client.get_object(**params)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        abort(416 if code == "InvalidRange" else 404)

    headers = {h: str(obj[k]) for h, k in (
        ("Content-Type", "ContentType"), ("Content-Length", "ContentLength"),
        ("Content-Range", "ContentRange"), ("Cache-Control", "CacheControl"), ("ETag", "ETag"),
    ) if obj.get(k) is not None}
    headers["Accept-Ranges"] = "bytes"
    status = 206 if "Content-Range" in headers else 200
    return Response(obj["Body"].iter_chunks(64 * 1024), status=status, headers=headers, direct_passthrough=True)


@bp.get("/cdn/<token>/<int:expires>/<video_id>/<path:path>")
def direct(token: str, expires: int, video_id: str, path: str):
    """Token-checked delivery when no edge proxy is deployed (CDN_MODE=direct)."""
    if not verify_edge_token(token, video_id, expires, current_app.config["CDN_SIGNING_SECRET"]):
        abort(410 if expires < time.time() else 403)
    return _stream_from_s3(video_id, path)


@bp.get("/origin/<video_id>/<path:path>")
def origin(video_id: str, path: str):
    """Custom origin for the edge cache. Only callers holding the shared secret
    (i.e. the edge itself) get through; the token was already checked at the edge."""
    secret = current_app.config["CDN_ORIGIN_SECRET"]
    if not secret or not hmac.compare_digest(request.headers.get("X-Origin-Secret", ""), secret):
        abort(403)
    return _stream_from_s3(video_id, path)
