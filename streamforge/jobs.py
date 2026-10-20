"""Background job dispatch. The transcode pipeline is plugged in during Phase 2."""

from __future__ import annotations

from flask import current_app


def enqueue_transcode(video_id: str) -> None:
    current_app.logger.info("upload complete, video %s queued for transcoding", video_id)
