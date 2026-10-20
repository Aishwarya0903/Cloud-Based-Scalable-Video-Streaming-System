"""Background job dispatch via Redis + RQ.

Workers are stateless and horizontally scalable: `docker compose up --scale worker=4`
adds transcode capacity with no code changes. Deterministic job ids make enqueueing
idempotent - a double-click on "complete" can't transcode the same video twice.
"""

from __future__ import annotations

from flask import current_app
from redis import Redis
from rq import Queue, Retry

JOB_TIMEOUT = 2 * 60 * 60


def get_queue() -> Queue:
    redis = Redis.from_url(current_app.config["REDIS_URL"])
    return Queue(current_app.config["QUEUE_NAME"], connection=redis)


def enqueue_transcode(video_id: str) -> None:
    if current_app.config["QUEUE_SYNC"]:
        from .tasks import process_video

        try:
            process_video(video_id)
        except Exception:  # noqa: BLE001 - already recorded on the video row
            current_app.logger.exception("inline transcode failed for %s", video_id)
        return

    queue = get_queue()
    job_id = f"transcode-{video_id}"
    existing = queue.fetch_job(job_id)
    if existing is not None and existing.get_status(refresh=True) in {"queued", "started", "deferred"}:
        return
    if existing is not None:
        existing.delete()
    queue.enqueue(
        "streamforge.tasks.process_video",
        video_id,
        job_id=job_id,
        job_timeout=JOB_TIMEOUT,
        retry=Retry(max=2, interval=[15, 60]),
        result_ttl=24 * 3600,
        failure_ttl=7 * 24 * 3600,
    )


def queue_depth() -> int | None:
    try:
        return get_queue().count
    except Exception:  # noqa: BLE001 - redis down shouldn't break callers
        return None
