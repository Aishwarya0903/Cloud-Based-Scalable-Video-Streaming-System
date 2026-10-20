"""Inspect an input file with ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class MediaError(Exception):
    """The input is not a usable video. Permanent - retrying will not help."""


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int   # display width (after rotation)
    height: int  # display height (after rotation)
    fps: float
    has_audio: bool
    video_codec: str


def _rotation(stream: dict) -> int:
    rotate = stream.get("tags", {}).get("rotate")
    if rotate is not None:
        return int(float(rotate)) % 360
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(float(side["rotation"])) % 360
    return 0


def _fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def parse_probe(data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("No video stream found in the file.")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaError("Video stream has no dimensions.")
    if _rotation(video) in (90, 270):  # phone footage: ffmpeg auto-rotates on decode
        width, height = height, width
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise MediaError("Could not determine the video duration.")
    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        fps=_fps(video.get("avg_frame_rate", "0/0")) or _fps(video.get("r_frame_rate", "0/0")),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        video_codec=video.get("codec_name", "unknown"),
    )


def probe(path: str) -> MediaInfo:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise MediaError(f"ffprobe could not read the file: {result.stderr.strip()[:300]}")
    return parse_probe(json.loads(result.stdout or "{}"))
