"""Viewer load test: browse, open a video, stream it through the edge, send QoE beacons.

    pip install locust
    locust -f loadtest/locustfile.py --host http://localhost:8080 \
           --users 100 --spawn-rate 10 --run-time 2m --headless

Everything goes through the edge (port 8080), exactly like real browsers. Note that
the analytics endpoint is rate-limited per client IP, and every simulated user shares
one IP, so run the stack with RATELIMIT_ENABLED=false when load testing.
"""

from __future__ import annotations

import random
import uuid
from urllib.parse import urljoin

from locust import HttpUser, between, task


class Viewer(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        items = self.client.get("/api/v1/videos?per_page=50", name="/api/v1/videos").json()["items"]
        self.video_ids = [v["id"] for v in items]

    @task(3)
    def browse(self) -> None:
        sort = random.choice(["recent", "popular", "title"])
        self.client.get(f"/api/v1/videos?sort={sort}", name="/api/v1/videos?sort=[sort]")
        self.client.get("/api/v1/trending", name="/api/v1/trending")

    @task(5)
    def watch(self) -> None:
        if not self.video_ids:
            return
        vid = random.choice(self.video_ids)
        self.client.get(f"/api/v1/videos/{vid}", name="/api/v1/videos/[id]")
        pb = self.client.get(f"/api/v1/videos/{vid}/playback", name="/api/v1/videos/[id]/playback").json()["playback"]

        master_url = pb["hls"]
        master = self.client.get(master_url, name="edge: master.m3u8").text
        variants = [line for line in master.splitlines() if line and not line.startswith("#")]
        variant_url = urljoin(master_url, random.choice(variants))
        playlist = self.client.get(variant_url, name="edge: variant .m3u8").text
        segments = [urljoin(variant_url, line) for line in playlist.splitlines()
                    if line and not line.startswith("#")]

        session = str(uuid.uuid4())
        events = f"/api/v1/videos/{vid}/events"
        self.client.post(events, json={"type": "start", "session_id": session, "startup_ms": random.randint(250, 900)},
                         name="/api/v1/videos/[id]/events")
        # Watch the first few segments, like a viewer who sticks around ~16 s.
        for seg in segments[: random.randint(2, 4)]:
            self.client.get(seg, name="edge: segment")
        self.client.post(events, json={"type": "heartbeat", "session_id": session, "watch_delta": 10,
                                       "from_position": 0, "position": 10, "bitrate": 2_800_000},
                         name="/api/v1/videos/[id]/events")
