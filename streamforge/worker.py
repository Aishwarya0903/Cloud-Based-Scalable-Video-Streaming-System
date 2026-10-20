"""Transcode worker entry point:  python -m streamforge.worker"""

from __future__ import annotations

from redis import Redis
from rq import Queue, Worker

from .tasks import _app


def main() -> None:
    app = _app()  # build once so every job reuses the same DB pool and S3 client
    redis = Redis.from_url(app.config["REDIS_URL"])
    queue = Queue(app.config["QUEUE_NAME"], connection=redis)
    with app.app_context():
        Worker([queue], connection=redis).work(with_scheduler=True)


if __name__ == "__main__":
    main()
