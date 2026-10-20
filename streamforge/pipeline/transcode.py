"""ffmpeg orchestration: one decode, many encodes.

`build_hls_command` produces a single ffmpeg invocation that decodes the source once,
splits it into N scaled outputs and writes an HLS rendition per rung plus a master
playlist. Keyframes are forced every SEGMENT_SECONDS on every rendition so segment
boundaries line up across qualities - that is what lets a player switch bitrate
mid-stream without a stall or visual glitch.
"""

from __future__ import annotations

import math
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .ladder import Rendition
from .probe import MediaError, MediaInfo

SEGMENT_SECONDS = 4
SPRITE_THUMB_WIDTH = 160
SPRITE_COLUMNS = 10
MAX_SPRITE_THUMBS = 100

ProgressFn = Callable[[float], None]


def build_hls_command(src: str, out_dir: str, info: MediaInfo, ladder: list[Rendition]) -> list[str]:
    n = len(ladder)
    split = f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n))
    scales = [
        f"[s{i}]scale=w={r.width}:h={r.height}:flags=lanczos,setsar=1[v{i}]"
        for i, r in enumerate(ladder)
    ]
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", src,
           "-filter_complex", ";".join([split, *scales])]

    for i, r in enumerate(ladder):
        cmd += [
            "-map", f"[v{i}]",
            f"-c:v:{i}", "libx264",
            f"-b:v:{i}", f"{r.video_kbps}k",
            f"-maxrate:v:{i}", f"{int(r.video_kbps * 1.1)}k",
            f"-bufsize:v:{i}", f"{r.video_kbps * 2}k",
        ]
        if info.has_audio:
            cmd += ["-map", "0:a:0", f"-c:a:{i}", "aac", f"-b:a:{i}", f"{r.audio_kbps}k", f"-ac:a:{i}", "2"]

    var_map = " ".join(
        f"v:{i},a:{i},name:{r.name}" if info.has_audio else f"v:{i},name:{r.name}"
        for i, r in enumerate(ladder)
    )
    cmd += [
        "-preset", "veryfast",
        "-profile:v", "main",
        "-pix_fmt", "yuv420p",
        "-sc_threshold", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})",
        "-f", "hls",
        "-hls_time", str(SEGMENT_SECONDS),
        "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", f"{out_dir}/%v/seg_%04d.ts",
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", var_map,
        "-progress", "pipe:1",
        "-nostats",
        f"{out_dir}/%v/index.m3u8",
    ]
    return cmd


def run_ffmpeg(cmd: list[str], duration: float, on_progress: ProgressFn | None = None,
               timeout: int = 3600) -> None:
    """Run ffmpeg, parsing `-progress` key=value lines into a 0-100 percentage."""
    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr_tail: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit() and on_progress and duration > 0:
                on_progress(min(99.0, int(value) / 1e6 / duration * 100))
            if time.monotonic() - start > timeout:
                proc.kill()
                raise MediaError("Transcoding timed out.")
        assert proc.stderr is not None
        stderr_tail = proc.stderr.read().splitlines()[-15:]
    finally:
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(stderr_tail))


def make_poster(src: str, dest: Path, info: MediaInfo) -> None:
    at = min(info.duration * 0.1, 5.0)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", f"{at:.2f}", "-i", src,
         "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", str(dest)],
        check=True, capture_output=True, timeout=120,
    )


def sprite_plan(info: MediaInfo) -> tuple[float, int, int, int]:
    """Return (interval_seconds, thumb_count, thumb_w, thumb_h) for the scrub sprite."""
    interval = max(1.0, math.ceil(info.duration / MAX_SPRITE_THUMBS))
    count = max(1, math.ceil(info.duration / interval))
    thumb_h = max(2, int(round(SPRITE_THUMB_WIDTH * info.height / info.width / 2)) * 2)
    return interval, count, SPRITE_THUMB_WIDTH, thumb_h


def make_sprite(src: str, out_dir: Path, info: MediaInfo) -> tuple[Path, Path]:
    """One JPEG grid of thumbnails + a WebVTT file mapping time ranges to tiles.

    Players use this for the hover preview on the seek bar (one image request
    instead of one per thumbnail).
    """
    interval, count, tw, th = sprite_plan(info)
    rows = math.ceil(count / SPRITE_COLUMNS)
    sprite = out_dir / "sprite.jpg"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", src, "-frames:v", "1", "-q:v", "5",
         "-vf", f"fps=1/{interval},scale={tw}:{th},tile={SPRITE_COLUMNS}x{rows}", str(sprite)],
        check=True, capture_output=True, timeout=600,
    )
    lines = ["WEBVTT", ""]
    for i in range(count):
        start, end = i * interval, min((i + 1) * interval, info.duration)
        x, y = (i % SPRITE_COLUMNS) * tw, (i // SPRITE_COLUMNS) * th
        lines += [f"{_ts(start)} --> {_ts(end)}", f"sprite.jpg#xywh={x},{y},{tw},{th}", ""]
    vtt = out_dir / "thumbnails.vtt"
    vtt.write_text("\n".join(lines))
    return sprite, vtt


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
