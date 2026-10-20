# ---- StreamForge API + worker image -------------------------------------------
# One image, two roles: `gunicorn` (API) or `python -m streamforge.worker` (transcoder).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# ffmpeg is needed by the transcode worker; curl for container health checks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY streamforge ./streamforge
COPY wsgi.py .
COPY deploy/gunicorn.conf.py ./deploy/gunicorn.conf.py

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /tmp/prometheus && chown app /tmp/prometheus
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["gunicorn", "wsgi:app", "-c", "deploy/gunicorn.conf.py"]
