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

## Phase 2 — Adaptive-bitrate transcoding (done)
- Redis + RQ worker pool, horizontally scalable (`docker compose up --scale worker=4`)
- **One-decode, many-encode ffmpeg pipeline** producing an H.264 HLS ladder (1080p → 240p)
  that never upscales, preserves aspect ratio and handles rotated phone footage
- Keyframes forced every 4 s on every rendition, so segments align and players switch quality seamlessly
- Poster frame + **seek-bar preview sprite with WebVTT** (one image request instead of hundreds)
- Live progress parsed from `ffmpeg -progress`, throttled DB writes
- Idempotent jobs (deterministic job IDs), retries for infra errors, fail-fast for bad media,
  owner-triggered re-transcode, `flask requeue-stuck` recovery command
- Immutable `Cache-Control` on segments, short TTL on playlists — ready for a CDN

## Phase 3 — CDN edge with signed URLs (done)
- **nginx edge cache as a local CloudFront stand-in**, the single public entry point on `:8080`
- **Path-scoped expiring tokens**: one signature in the URL path authorises the master playlist
  *and* every relatively-referenced segment; validated at the edge (`secure_link`) so bad or
  expired links never reach the origin (403 / 410)
- Token-free cache key → every viewer shares one cached copy; `proxy_cache_lock` collapses a
  thundering herd into a single origin fetch; stale-while-revalidate on origin errors
- Internal custom origin protected by a shared-secret header (the CloudFront custom-origin pattern)
- **Production mode: CloudFront signed URLs** with a wildcard custom policy over `hls/<id>/*`
- `direct` mode for running without nginx; HTTP range requests (206) end to end
- `scripts/cdn_bench.py` measures cold vs warm delivery

| Measured locally (20 concurrent viewers, 720p) | Result |
|---|---|
| Playlist MISS → HIT | 29 ms → 0.7 ms |
| 1.5 MB segment MISS → HIT | 18 ms → 2 ms |
| Cold cache, 140 simultaneous requests | 96.4 % served from cache (5 origin fetches) |

## Run it
```bash
docker compose up --build          # app + edge on http://localhost:8080
# or without Docker:
pip install -r requirements-dev.txt && pytest
```
