#!/usr/bin/env python3
"""Measure edge-cache behaviour: cold (MISS) vs warm (HIT) delivery of a whole video.

Simulates N concurrent viewers fetching the master playlist, one rendition playlist and
every segment of that rendition through the edge. Standard library only.

    python scripts/cdn_bench.py --base http://localhost:8080 --video <video_id> --viewers 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin


def fetch(url: str) -> tuple[float, int, str]:
    start = time.perf_counter()
    with urllib.request.urlopen(url, timeout=30) as resp:
        size = len(resp.read())
        status = resp.headers.get("X-Cache-Status", "-")
    return (time.perf_counter() - start) * 1000, size, status


def video_urls(base: str, video_id: str, rendition: str | None) -> list[str]:
    with urllib.request.urlopen(f"{base}/api/v1/videos/{video_id}/playback") as resp:
        master = urljoin(base, json.load(resp)["playback"]["hls"])
    lines = urllib.request.urlopen(master).read().decode().splitlines()
    variants = [line for line in lines if line and not line.startswith("#")]
    variant = urljoin(master, next((v for v in variants if rendition and rendition in v), variants[0]))
    segs = [urljoin(variant, line) for line in urllib.request.urlopen(variant).read().decode().splitlines()
            if line and not line.startswith("#")]
    return [master, variant, *segs]


def run(urls: list[str], viewers: int) -> list[tuple[float, int, str]]:
    jobs = [u for _ in range(viewers) for u in urls]
    with ThreadPoolExecutor(max_workers=viewers) as pool:
        return list(pool.map(fetch, jobs))


def report(label: str, results: list[tuple[float, int, str]], wall: float) -> None:
    ms = sorted(r[0] for r in results)
    hits = sum(1 for r in results if r[2] == "HIT")
    mb = sum(r[1] for r in results) / 1e6
    p95 = ms[int(len(ms) * 0.95) - 1]
    print(f"{label:<6} requests={len(ms):<5} p50={statistics.median(ms):7.2f}ms p95={p95:7.2f}ms "
          f"hit_ratio={hits / len(ms):6.1%} throughput={mb / wall:7.1f} MB/s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--video", required=True)
    ap.add_argument("--rendition", default="720p")
    ap.add_argument("--viewers", type=int, default=10)
    args = ap.parse_args()

    urls = video_urls(args.base, args.video, args.rendition)
    print(f"{len(urls)} objects per viewer, {args.viewers} concurrent viewers\n")
    for label in ("cold", "warm"):
        t = time.perf_counter()
        results = run(urls, args.viewers)
        report(label, results, time.perf_counter() - t)


if __name__ == "__main__":
    main()
