"""Direct-to-S3 resumable multipart uploads.

Video bytes never pass through Flask. The API only:
  1. plans the upload and opens an S3 multipart upload      POST /uploads
  2. signs short-lived URLs for batches of parts            POST /uploads/<id>/parts
  3. reports which parts S3 already has (for resume)        GET  /uploads/<id>
  4. completes it - using S3's own part list, not the
     client's, so a client cannot forge ETags              POST /uploads/<id>/complete
  5. aborts it                                              DELETE /uploads/<id>

The browser PUTs each part straight to S3 in parallel. This keeps API workers free,
removes the API as a bandwidth bottleneck, and lets uploads scale with S3.
"""

from __future__ import annotations

import math
import os

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_auth
from ..errors import APIError
from ..extensions import db
from ..models import Video, VideoStatus, Visibility
from ..storage import get_storage

bp = Blueprint("uploads", __name__, url_prefix="/api/v1/uploads")

S3_MIN_PART = 5 * 1024 * 1024  # S3 minimum for every part except the last
S3_MAX_PARTS = 10_000
SIGN_BATCH_LIMIT = 100


def plan_parts(size: int, preferred: int) -> tuple[int, int]:
    """Choose a part size that respects S3's limits (>=5 MiB, <=10,000 parts)."""
    part_size = max(preferred, S3_MIN_PART, math.ceil(size / S3_MAX_PARTS))
    return part_size, max(1, math.ceil(size / part_size))


def _owned_upload(video_id: str) -> Video:
    video = db.session.get(Video, video_id)
    if video is None or video.owner_id != g.user.id:
        raise APIError(404, "not_found", "Upload not found.")
    return video


def _require_uploading(video: Video) -> None:
    if video.status != VideoStatus.UPLOADING or not video.upload_id:
        raise APIError(409, "upload_closed", f"Upload is already {video.status}.")


@bp.post("")
@require_auth
def create_upload():
    data = request.get_json(silent=True) or {}
    cfg = current_app.config
    filename = os.path.basename(str(data.get("filename", "")).strip())[:255]
    content_type = str(data.get("content_type", "")).lower()
    title = str(data.get("title", "")).strip() or os.path.splitext(filename)[0]
    visibility = str(data.get("visibility", Visibility.PUBLIC))
    try:
        size = int(data.get("size", 0))
    except (TypeError, ValueError):
        size = 0

    if not filename:
        raise APIError(422, "invalid_filename", "filename is required.")
    if content_type not in cfg["ALLOWED_VIDEO_TYPES"]:
        raise APIError(
            415,
            "unsupported_type",
            "That file type is not supported.",
            allowed=sorted(cfg["ALLOWED_VIDEO_TYPES"]),
        )
    if size <= 0 or size > cfg["MAX_UPLOAD_BYTES"]:
        raise APIError(413, "invalid_size", "File is empty or too large.", max=cfg["MAX_UPLOAD_BYTES"])
    if visibility not in Visibility.ALL:
        raise APIError(422, "invalid_visibility", f"visibility must be one of {Visibility.ALL}.")

    part_size, part_count = plan_parts(size, cfg["UPLOAD_PART_SIZE"])
    video = Video(
        owner_id=g.user.id,
        title=title[:200],
        description=str(data.get("description", ""))[:5000],
        visibility=visibility,
        original_filename=filename,
        content_type=content_type,
        size_bytes=size,
        part_size=part_size,
        part_count=part_count,
        raw_key="",
    )
    ext = os.path.splitext(filename)[1].lower()[:10] or ".mp4"
    video.raw_key = f"uploads/{g.user.id}/{video.id}{ext}"
    video.upload_id = get_storage().create_multipart_upload(video.raw_key, content_type)
    db.session.add(video)
    db.session.commit()

    return jsonify(
        {
            "video_id": video.id,
            "part_size": part_size,
            "part_count": part_count,
            "sign_batch_limit": SIGN_BATCH_LIMIT,
            "expires_in": cfg["PRESIGN_TTL_SECONDS"],
        }
    ), 201


@bp.post("/<video_id>/parts")
@require_auth
def sign_parts(video_id: str):
    video = _owned_upload(video_id)
    _require_uploading(video)
    numbers = (request.get_json(silent=True) or {}).get("part_numbers") or []
    if not isinstance(numbers, list) or not numbers or len(numbers) > SIGN_BATCH_LIMIT:
        raise APIError(422, "invalid_parts", f"Send 1-{SIGN_BATCH_LIMIT} part_numbers.")
    try:
        numbers = sorted({int(n) for n in numbers})
    except (TypeError, ValueError) as exc:
        raise APIError(422, "invalid_parts", "part_numbers must be integers.") from exc
    if numbers[0] < 1 or numbers[-1] > video.part_count:
        raise APIError(422, "invalid_parts", f"Parts must be between 1 and {video.part_count}.")

    storage = get_storage()
    urls = {n: storage.presign_part(video.raw_key, video.upload_id, n) for n in numbers}
    return jsonify({"urls": urls, "expires_in": current_app.config["PRESIGN_TTL_SECONDS"]})


@bp.get("/<video_id>")
@require_auth
def upload_status(video_id: str):
    """Lets a client resume after a crash, refresh or network drop."""
    video = _owned_upload(video_id)
    uploaded: list[int] = []
    if video.status == VideoStatus.UPLOADING and video.upload_id:
        uploaded = [p["PartNumber"] for p in get_storage().list_parts(video.raw_key, video.upload_id)]
    return jsonify(
        {
            "video_id": video.id,
            "status": video.status,
            "part_size": video.part_size,
            "part_count": video.part_count,
            "uploaded_parts": uploaded,
        }
    )


@bp.post("/<video_id>/complete")
@require_auth
def complete_upload(video_id: str):
    video = _owned_upload(video_id)
    _require_uploading(video)
    storage = get_storage()

    parts = storage.list_parts(video.raw_key, video.upload_id)
    received = {p["PartNumber"] for p in parts}
    missing = sorted(set(range(1, video.part_count + 1)) - received)
    if missing:
        raise APIError(409, "parts_missing", "Some parts have not been uploaded.", missing=missing[:50])
    if sum(p["Size"] for p in parts) != video.size_bytes:
        raise APIError(409, "size_mismatch", "Uploaded bytes do not match the declared size.")

    storage.complete_multipart_upload(video.raw_key, video.upload_id, parts)
    video.upload_id = None
    video.status = VideoStatus.QUEUED
    db.session.commit()

    from ..jobs import enqueue_transcode  # local import avoids a cycle

    enqueue_transcode(video.id)
    db.session.refresh(video)
    return jsonify({"video": video.to_dict(private=True)}), 202


@bp.delete("/<video_id>")
@require_auth
def abort_upload(video_id: str):
    video = _owned_upload(video_id)
    _require_uploading(video)
    get_storage().abort_multipart_upload(video.raw_key, video.upload_id)
    db.session.delete(video)
    db.session.commit()
    return "", 204
