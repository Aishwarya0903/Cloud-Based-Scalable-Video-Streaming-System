"""Adaptive-bitrate ladder selection.

Each rung is an H.264 rendition. We only emit rungs at or below the source height
(upscaling wastes storage and CDN bandwidth with zero quality gain) and keep the
source aspect ratio. Bitrates follow common streaming-industry ladders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Rung:
    name: str
    height: int
    video_kbps: int
    audio_kbps: int


DEFAULT_LADDER: tuple[Rung, ...] = (
    Rung("1080p", 1080, 5000, 160),
    Rung("720p", 720, 2800, 128),
    Rung("480p", 480, 1400, 128),
    Rung("360p", 360, 800, 96),
    Rung("240p", 240, 400, 64),
)


@dataclass(frozen=True)
class Rendition:
    name: str
    width: int
    height: int
    video_kbps: int
    audio_kbps: int

    @property
    def bandwidth(self) -> int:
        """Peak bits/s, as advertised in the HLS master playlist."""
        return int((self.video_kbps * 1.1 + self.audio_kbps) * 1000)

    def to_dict(self) -> dict:
        return asdict(self) | {"bandwidth": self.bandwidth}


def _even(n: float) -> int:
    return max(2, int(round(n / 2)) * 2)  # H.264 4:2:0 needs even dimensions


def build_ladder(
    src_width: int, src_height: int, ladder: tuple[Rung, ...] = DEFAULT_LADDER, max_rungs: int = 4
) -> list[Rendition]:
    # Treat portrait video by its short side so a 1080x1920 phone clip gets "1080p".
    short_side = min(src_width, src_height)
    portrait = src_height > src_width
    rungs = [r for r in ladder if r.height <= short_side][:max_rungs]
    if not rungs:  # tiny source: one rendition at native size
        smallest = ladder[-1]
        return [Rendition(f"{short_side}p", _even(src_width), _even(src_height),
                          smallest.video_kbps, smallest.audio_kbps)]

    out = []
    for r in rungs:
        long_side = _even(r.height * max(src_width, src_height) / short_side)
        w, h = (r.height, long_side) if portrait else (long_side, r.height)
        out.append(Rendition(r.name, _even(w), _even(h), r.video_kbps, r.audio_kbps))
    return out
