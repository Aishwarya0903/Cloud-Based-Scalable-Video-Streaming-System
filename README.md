# StreamForge — Cloud-Based Scalable Video Streaming System

A cloud-native video streaming platform built with **Python/Flask** and **AWS S3 + CloudFront**
(S3-compatible MinIO locally). Being built in phases; see the commit history.

## Phase 1 — Core API (done)
- Flask app factory, SQLAlchemy models, JSON error contract, JWT auth
- **Direct-to-S3 resumable multipart uploads**: the browser PUTs parts in parallel to presigned
  URLs; the API never handles video bytes. Completion uses S3's own part list (no client-forged ETags)
- Video library with search, sorting, pagination and public / unlisted / private visibility
- Liveness `/healthz` and readiness `/readyz` probes
- Docker Compose stack: API, PostgreSQL, Redis, MinIO — all free
- pytest suite against mocked S3 (moto)

## Run it
```bash
docker compose up --build          # API on http://localhost:8000
# or without Docker:
pip install -r requirements-dev.txt && pytest
```
