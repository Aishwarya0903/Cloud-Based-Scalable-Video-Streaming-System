"""Gunicorn settings. Metrics from every worker process are merged via
PROMETHEUS_MULTIPROC_DIR; these hooks keep that directory consistent."""

import glob
import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"  # video bytes never touch the API, so requests are short and I/O-bound
preload_app = True
accesslog = None  # the app logs API requests itself, with request IDs
timeout = 30
graceful_timeout = 20

# Runs when gunicorn reads this file - before preload_app imports the app and its
# metrics - so the directory exists and holds no samples from a previous run.
_metrics_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
if _metrics_dir:
    os.makedirs(_metrics_dir, exist_ok=True)
    for _stale in glob.glob(os.path.join(_metrics_dir, "*.db")):
        os.remove(_stale)


def child_exit(server, worker):
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
