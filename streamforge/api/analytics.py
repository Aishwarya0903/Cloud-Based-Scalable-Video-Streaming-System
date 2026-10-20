"""Quality-of-experience analytics from player beacons.

The player posts small events while someone watches:
  start      first frame rendered (carries startup time)
  heartbeat  every ~10 s: seconds watched, stalls, quality switches, bitrate, position
  end        page hidden / video finished (sent with navigator.sendBeacon)

Events are folded into one PlaybackSession row per viewing, so the write load is a
single upsert per beacon, and every metric below is a cheap aggregate.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from ..auth import optional_auth, require_auth
from ..errors import APIError
from ..extensions import db, limiter
from ..metrics import QOE_REBUFFER, QOE_STARTUP, VIEWS
from ..models import RETENTION_BUCKETS, PlaybackSession, Video, VideoStatus, Visibility, utcnow

bp = Blueprint("analytics", __name__, url_prefix="/api/v1")

SESSION_ID = re.compile(r"^[0-9a-f-]{16,36}$")
EVENT_TYPES = {"start", "heartbeat", "end"}
TRENDING_WINDOW = timedelta(days=3)
TRENDING_HALF_LIFE_H = 24.0


def _num(data: dict, key: str, lo: float, hi: float) -> float:
    try:
        value = float(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(hi, max(lo, value)) if math.isfinite(value) else 0.0


@bp.post("/videos/<video_id>/events")
@limiter.limit("120/minute")
@optional_auth
def ingest(video_id: str):
    # sendBeacon posts text/plain, so parse the body regardless of content type.
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "invalid_event", "Body must be a JSON object.")
    kind, sid = data.get("type"), str(data.get("session_id", ""))
    if kind not in EVENT_TYPES or not SESSION_ID.match(sid):
        raise APIError(422, "invalid_event", "Unknown event type or session id.")

    video = db.session.get(Video, video_id)
    if video is None or not video.can_view(g.user) or not video.duration_s:
        raise APIError(404, "not_found", "Video not found.")

    session = db.session.get(PlaybackSession, sid)
    if session is None:
        if kind != "start":
            return "", 204  # heartbeat for an unknown session (e.g. DB was reset) - ignore
        session = PlaybackSession(
            id=sid, video_id=video.id, viewer_id=g.user.id if g.user else None,
            watch_seconds=0.0, rebuffer_ms=0, rebuffer_count=0, quality_switches=0,
            bitrate_sum=0.0, watched_mask=0, completed=False,
        )
        db.session.add(session)
        video.view_count = (video.view_count or 0) + 1
        VIEWS.inc()
    elif session.video_id != video.id:
        raise APIError(409, "session_mismatch", "Session belongs to another video.")

    if kind == "start":
        startup = int(_num(data, "startup_ms", 0, 60_000))
        if startup and session.startup_ms is None:
            session.startup_ms = startup
            QOE_STARTUP.observe(startup / 1000)

    # Deltas are clamped so a buggy or hostile client can't skew the aggregates much.
    watched = _num(data, "watch_delta", 0, 60)
    stall_ms = int(_num(data, "rebuffer_ms_delta", 0, 60_000))
    session.watch_seconds += watched
    session.rebuffer_ms += stall_ms
    session.rebuffer_count += int(_num(data, "rebuffer_count_delta", 0, 50))
    session.quality_switches += int(_num(data, "switches_delta", 0, 50))
    session.bitrate_sum += _num(data, "bitrate", 0, 100_000_000) * watched
    if watched or stall_ms:
        QOE_REBUFFER.observe(stall_ms / 1000 / max(watched + stall_ms / 1000, 0.001))

    position = _num(data, "position", 0, video.duration_s)
    from_pos = _num(data, "from_position", 0, video.duration_s) if "from_position" in data else position
    session.watched_mask |= _mask(min(from_pos, position), position, video.duration_s)
    if position >= video.duration_s * 0.95 or kind == "end" and data.get("finished"):
        session.completed = True
    session.last_seen = utcnow()
    db.session.commit()
    return "", 204


def _mask(start: float, end: float, duration: float) -> int:
    """Bitmask of the 5% slices covered by [start, end]."""
    first = min(RETENTION_BUCKETS - 1, int(start / duration * RETENTION_BUCKETS))
    last = min(RETENTION_BUCKETS - 1, int(end / duration * RETENTION_BUCKETS))
    mask = 0
    for b in range(first, last + 1):
        mask |= 1 << b
    return mask


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summarize(sessions: list[PlaybackSession], duration: float | None) -> dict:
    n = len(sessions)
    watch = sum(s.watch_seconds for s in sessions)
    stall = sum(s.rebuffer_ms for s in sessions) / 1000
    startups = [s.startup_ms for s in sessions if s.startup_ms is not None]
    viewers = {s.viewer_id or s.id for s in sessions}
    retention = [
        round(sum(1 for s in sessions if s.watched_mask >> b & 1) / n * 100, 1) if n else 0.0
        for b in range(RETENTION_BUCKETS)
    ]
    return {
        "views": n,
        "unique_viewers": len(viewers),
        "watch_time_seconds": round(watch, 1),
        "avg_watch_seconds": round(watch / n, 1) if n else 0.0,
        "avg_percent_watched": round(watch / n / duration * 100, 1) if n and duration else 0.0,
        "completion_rate": round(sum(s.completed for s in sessions) / n * 100, 1) if n else 0.0,
        "startup_ms_p50": _percentile(startups, 0.5),
        "startup_ms_p95": _percentile(startups, 0.95),
        # Share of viewing time spent stalled - the single most important QoE number.
        "rebuffer_ratio": round(stall / (watch + stall) * 100, 2) if watch + stall else 0.0,
        "sessions_with_stalls": round(sum(1 for s in sessions if s.rebuffer_count) / n * 100, 1) if n else 0.0,
        "avg_bitrate_bps": round(sum(s.bitrate_sum for s in sessions) / watch) if watch else None,
        "avg_quality_switches": round(statistics.fmean(s.quality_switches for s in sessions), 2) if n else 0.0,
        "retention": retention,
    }


@bp.get("/videos/<video_id>/stats")
@require_auth
def video_stats(video_id: str):
    video = db.session.get(Video, video_id)
    if video is None or video.owner_id != g.user.id:
        raise APIError(404, "not_found", "Video not found.")
    sessions = db.session.scalars(select(PlaybackSession).where(PlaybackSession.video_id == video.id)).all()
    return jsonify({"video": video.to_dict(private=True), "stats": summarize(list(sessions), video.duration_s)})


@bp.get("/trending")
def trending():
    """Engagement-weighted, time-decayed ranking (half-life 24 h) over the last 3 days.

    A view counts for more the longer it was watched (capped), and recent views count
    for more than old ones - so a burst of real watching rises quickly and fades.
    """
    now = utcnow()
    rows = db.session.execute(
        select(PlaybackSession.video_id, PlaybackSession.started_at, PlaybackSession.watch_seconds)
        .join(Video, Video.id == PlaybackSession.video_id)
        .where(PlaybackSession.started_at >= now - TRENDING_WINDOW,
               Video.status == VideoStatus.READY, Video.visibility == Visibility.PUBLIC)
    ).all()
    scores: dict[str, float] = {}
    for vid, started, watched in rows:
        age_h = (now - started).total_seconds() / 3600
        weight = 1 + min(watched, 600) / 60
        scores[vid] = scores.get(vid, 0.0) + weight * 0.5 ** (age_h / TRENDING_HALF_LIFE_H)
    top = sorted(scores, key=scores.get, reverse=True)[:12]
    videos = {v.id: v for v in db.session.scalars(select(Video).where(Video.id.in_(top)))} if top else {}

    from ..cdn import playback_for

    items = []
    for vid in top:
        data = videos[vid].to_dict()
        data["poster_url"] = playback_for(vid).poster
        data["trending_score"] = round(scores[vid], 2)
        items.append(data)
    return jsonify({"items": items, "half_life_hours": TRENDING_HALF_LIFE_H})
