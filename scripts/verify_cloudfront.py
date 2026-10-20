#!/usr/bin/env python3
"""Prove the deployed CloudFront distribution behaves as designed.

Uploads a tiny test playlist to the media bucket, then checks through CloudFront that:
  1. an unsigned request is refused              (403 - media is not public)
  2. S3 cannot be read directly                  (403 - bucket is private, OAC only)
  3. a signed request is served                  (200)
  4. a repeat request is served from the edge    (X-Cache: Hit from cloudfront)
  5. the signature in the URL is not part of the cache key (fresh signature still Hits)
and finally removes the test object.

    set -a; . ./.env.aws; set +a
    python scripts/verify_cloudfront.py
"""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamforge import create_app  # noqa: E402
from streamforge.cdn import playback_for  # noqa: E402


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            resp.read()
            return resp.status, resp.headers.get("X-Cache", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("X-Cache", "")


def check(label: str, ok: bool, detail: str) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label:<46} {detail}")
    return ok


def main() -> int:
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    if app.config["CDN_MODE"] != "cloudfront":
        print("Set CDN_MODE=cloudfront (load .env.aws first).")
        return 2

    with app.app_context():
        storage = app.extensions["storage"]
        vid = str(uuid.uuid4())
        key = f"hls/{vid}/master.m3u8"
        storage.client.put_object(Bucket=storage.media_bucket, Key=key, Body=b"#EXTM3U\n#EXT-X-VERSION:3\n",
                                  ContentType="application/vnd.apple.mpegurl", CacheControl="public, max-age=60")
        try:
            signed = playback_for(vid).hls
            base = signed.split("?", 1)[0]
            region = app.config["AWS_REGION"]
            direct = f"https://{storage.media_bucket}.s3.{region}.amazonaws.com/{key}"

            results = []
            status, _ = get(base)
            results.append(check("unsigned CloudFront request refused", status == 403, f"HTTP {status}"))
            status, _ = get(direct)
            results.append(check("direct S3 read refused", status == 403, f"HTTP {status}"))
            status, cache1 = get(signed)
            results.append(check("signed request served", status == 200, f"HTTP {status}, {cache1 or 'no X-Cache'}"))
            time.sleep(1)
            status, cache2 = get(signed)
            results.append(check("repeat request served from edge cache", "Hit" in cache2, cache2 or "no X-Cache"))
            status, cache3 = get(playback_for(vid, ttl=900).hls)
            results.append(check("new signature shares the cached copy", "Hit" in cache3, cache3 or "no X-Cache"))
        finally:
            storage.delete_object(storage.media_bucket, key)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
