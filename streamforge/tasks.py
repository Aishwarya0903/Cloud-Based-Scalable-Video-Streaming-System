"""The transcode job executed by RQ workers (or inline when QUEUE_SYNC=true)."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, current_app, has_app_context

from .extensions import db
from .models import Video, VideoStatus, utcnow
from .pipeline.ladder import build_ladder
from .pipeline.probe import MediaError, probe
from .pipeline.transcode import build_hls_command, make_poster, make_sprite, run_ffmpeg
from .storage import get_storage

log = logging.getLogger("streamforge.tasks")

MAX_DURATION_S = 3 * 60 * 60
# Segments, posters and sprites never change once written -> cache "forever" at the edge.
IMMUTABLE = "public, max-age=31536000, immutable"
# Playlists are tiny; a short TTL keeps re-transcodes visible quickly.
PLAYLIST = "public, max-age=60"

_worker_app: Flask | None = None


def _app() -> Flask:
    global _worker_app
    if _worker_app is None:
        from . import create_app

        _worker_app = create_app()
    return _worker_app


def process_video(video_id: str) -> dict:
    if has_app_context():
        return _process(video_id)
    with _app().app_context():
        return _process(video_id)


class _Progress:
    """Throttled progress writer - one DB update every ~2s, not one per ffmpeg tick."""

    def __init__(self, video: Video, every: float = 2.0):
        self.video, self.every, self.last = video, every, 0.0

    def __call__(self, pct: float) -> None:
        now = time.monotonic()
        if now - self.last >= self.every:
            self.last = now
            self.video.progress = pct
            db.session.commit()


def _cache_control(key: str) -> str:
    return PLAYLIST if key.endswith(".m3u8") else IMMUTABLE


def _process(video_id: str) -> dict:
    video = db.session.get(Video, video_id)
    if video is None:
        log.warning("video %s vanished before processing", video_id)
        return {"status": "skipped"}

    storage = get_storage()
    started = time.monotonic()
    video.status, video.progress, video.error = VideoStatus.PROCESSING, 0.0, None
    db.session.commit()
    work = Path(tempfile.mkdtemp(prefix=f"sf-{video_id[:8]}-"))
    try:
        src = work / f"source{Path(video.raw_key).suffix or '.mp4'}"
        storage.download_file(storage.raw_bucket, video.raw_key, src)

        info = probe(str(src))
        if info.duration > MAX_DURATION_S:
            raise MediaError("Videos longer than 3 hours are not supported.")
        ladder = build_ladder(info.width, info.height)

        out = work / "out"
        out.mkdir()
        run_ffmpeg(build_hls_command(str(src), str(out), info, ladder), info.duration, _Progress(video))
        make_poster(str(src), out / "poster.jpg", info)
        make_sprite(str(src), out, info)

        # Re-runs are idempotent: clear old assets, then upload in parallel.
        storage.delete_prefix(storage.media_bucket, video.media_prefix)
        files = [p for p in out.rglob("*") if p.is_file()]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(
                lambda p: storage.upload_file(
                    p, storage.media_bucket, video.media_prefix + p.relative_to(out).as_posix(),
                    cache_control=_cache_control(p.name),
                ),
                files,
            ))

        video.duration_s = round(info.duration, 3)
        video.width, video.height = info.width, info.height
        video.renditions = [r.to_dict() for r in ladder]
        video.status, video.progress = VideoStatus.READY, 100.0
        video.ready_at = utcnow()
        video.processing_seconds = round(time.monotonic() - started, 2)
        db.session.commit()
        log.info("video %s ready: %s in %.1fs", video_id, [r.name for r in ladder], video.processing_seconds)
        return {"status": "ready", "renditions": len(ladder), "objects": len(files)}

    except MediaError as exc:  # bad input: fail fast, do not retry
        _fail(video, str(exc))
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:  # infrastructure error: mark failed and let RQ retry
        _fail(video, "Processing error, retrying." if not current_app.config["QUEUE_SYNC"] else str(exc)[:500])
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if not current_app.config["QUEUE_SYNC"]:
            db.session.remove()  # fresh session per job in long-lived workers


def _fail(video: Video, message: str) -> None:
    db.session.rollback()
    video.status, video.error = VideoStatus.FAILED, message[:1000]
    db.session.commit()
    log.warning("video %s failed: %s", video.id, message)
