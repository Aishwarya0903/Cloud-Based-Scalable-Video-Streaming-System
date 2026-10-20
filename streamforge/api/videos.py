from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_, select

from ..auth import optional_auth, require_auth
from ..errors import APIError
from ..extensions import db
from ..models import Video, VideoStatus, Visibility
from ..storage import get_storage

bp = Blueprint("videos", __name__, url_prefix="/api/v1")

SORTS = {
    "recent": Video.created_at.desc(),
    "popular": Video.view_count.desc(),
    "title": Video.title.asc(),
}


def _page_args() -> tuple[int, int]:
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("per_page", 12))))
    except ValueError as exc:
        raise APIError(422, "invalid_paging", "page and per_page must be integers.") from exc
    return page, per_page


def _paginate(stmt, private: bool = False):
    page, per_page = _page_args()
    result = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return jsonify(
        {
            "items": [v.to_dict(private=private) for v in result.items],
            "page": page,
            "per_page": per_page,
            "total": result.total,
            "pages": result.pages,
        }
    )


def get_video_or_404(video_id: str) -> Video:
    video = db.session.get(Video, video_id)
    if video is None or not video.can_view(g.get("user")):
        raise APIError(404, "not_found", "Video not found.")
    return video


@bp.get("/videos")
@optional_auth
def list_videos():
    """Public library: ready + public videos, searchable and sortable."""
    stmt = select(Video).where(
        Video.status == VideoStatus.READY, Video.visibility == Visibility.PUBLIC
    )
    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(Video.title.ilike(like), Video.description.ilike(like)))
    sort = request.args.get("sort", "recent")
    if sort not in SORTS:
        raise APIError(422, "invalid_sort", f"sort must be one of {sorted(SORTS)}.")
    return _paginate(stmt.order_by(SORTS[sort]))


@bp.get("/me/videos")
@require_auth
def my_videos():
    stmt = select(Video).where(Video.owner_id == g.user.id).order_by(Video.created_at.desc())
    status = request.args.get("status")
    if status:
        stmt = stmt.where(Video.status == status)
    return _paginate(stmt, private=True)


@bp.get("/videos/<video_id>")
@optional_auth
def get_video(video_id: str):
    video = get_video_or_404(video_id)
    is_owner = g.user is not None and g.user.id == video.owner_id
    return jsonify({"video": video.to_dict(private=is_owner)})


@bp.patch("/videos/<video_id>")
@require_auth
def update_video(video_id: str):
    video = get_video_or_404(video_id)
    if video.owner_id != g.user.id:
        raise APIError(403, "forbidden", "Only the owner can edit this video.")
    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = str(data["title"]).strip()
        if not title:
            raise APIError(422, "invalid_title", "Title cannot be empty.")
        video.title = title[:200]
    if "description" in data:
        video.description = str(data["description"])[:5000]
    if "visibility" in data:
        if data["visibility"] not in Visibility.ALL:
            raise APIError(422, "invalid_visibility", f"visibility must be one of {Visibility.ALL}.")
        video.visibility = data["visibility"]
    db.session.commit()
    return jsonify({"video": video.to_dict(private=True)})


@bp.delete("/videos/<video_id>")
@require_auth
def delete_video(video_id: str):
    video = get_video_or_404(video_id)
    if video.owner_id != g.user.id:
        raise APIError(403, "forbidden", "Only the owner can delete this video.")
    storage = get_storage()
    if video.upload_id:
        storage.abort_multipart_upload(video.raw_key, video.upload_id)
    storage.delete_object(storage.raw_bucket, video.raw_key)
    removed = storage.delete_prefix(storage.media_bucket, video.media_prefix)
    db.session.delete(video)
    db.session.commit()
    current_app.logger.info("deleted video %s (%d media objects)", video_id, removed)
    return "", 204
