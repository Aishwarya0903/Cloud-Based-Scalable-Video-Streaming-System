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

## Phase 4 — AWS infrastructure as code: S3 + CloudFront (done)
Terraform in [`infra/terraform`](infra/terraform/README.md) provisions the production delivery path:
- **CloudFront distribution** in front of a private media bucket via **Origin Access Control**
  (S3 is never public; direct reads get 403)
- Separate **cache policies**: 60 s for HLS playlists, 1 year for immutable segments/posters/sprites;
  HTTP/2 + HTTP/3, IPv6, gzip/brotli, HTTPS-only, `PriceClass_100`
- **Signed URLs** via a CloudFront key group; the API signs a wildcard policy per video, and
  signatures are excluded from the cache key so every viewer shares the edge cache
- Response headers policy for HLS-player CORS + HSTS
- Raw-upload bucket with browser CORS, SSE-S3 encryption, and lifecycle rules that abort stale
  multipart uploads and expire originals (cost control)
- Least-privilege IAM policy for the app; optional $1/month AWS Budget alert
- `docker-compose.aws.yml` runs the same app against real AWS; `scripts/verify_cloudfront.py`
  proves the live distribution (unsigned 403, S3 direct 403, signed 200, edge cache Hit)
- **GitHub Actions CI**: ruff + pytest (Python 3.10 & 3.12, real ffmpeg), `terraform fmt`/`validate`,
  Docker build

All of it fits the AWS Free Tier for a demo (CloudFront: 1 TB/month always free).

## Phase 5 — Web player and upload studio (done)
![Watch page: player with the live rendition ladder](docs/screenshots/watch.jpg)

- **Adaptive player** on hls.js (vendored, no third-party CDN): custom controls, keyboard shortcuts
  (space/k, j/l, m, f), seek-bar **thumbnail previews** from the sprite + WebVTT
- **Live rendition ladder** beside the player: highlights the rung actually playing as hls.js switches,
  click a rung to lock quality; live bandwidth estimate, buffer, startup time and switch count
- Works with all three delivery modes; in CloudFront mode the signed query rides on every
  playlist/segment request
- **Upload page** with a live grid of multipart parts, 4 parallel PUTs straight to S3, retries
  with backoff, automatic re-signing of expired URLs, and **resume after reload**
  (asks S3 which parts it already has), then live transcode progress
- "Your videos" studio: status, progress, re-process, delete; library with search, sort, paging
- Responsive down to phone width, visible keyboard focus, reduced-motion support, dark mode

Measured locally: a 24 MB 1080p clip uploaded in 0.8 s (4 parallel parts); 40 s of 1080p
became a 4-rung ladder in 89 s on a 2-vCPU container; playback started in about 0.5 s.

## Run it
```bash
docker compose up --build          # open http://localhost:8080
# or without Docker:
pip install -r requirements-dev.txt && pytest
```
