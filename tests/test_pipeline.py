import shutil
import subprocess
from pathlib import Path

import pytest

from streamforge.extensions import db
from streamforge.models import Video, VideoStatus
from streamforge.pipeline.ladder import build_ladder
from streamforge.pipeline.probe import MediaError, MediaInfo, parse_probe
from streamforge.pipeline.transcode import _ts, build_hls_command, sprite_plan

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


# ---------------------------------------------------------------- ladder
def test_ladder_never_upscales():
    names = [r.name for r in build_ladder(1280, 720)]
    assert names == ["720p", "480p", "360p", "240p"]
    assert all(r.height <= 720 for r in build_ladder(1280, 720))


def test_ladder_keeps_aspect_and_even_dims():
    for r in build_ladder(1920, 800):  # 2.4:1 cinema
        assert r.width % 2 == 0 and r.height % 2 == 0
        assert abs(r.width / r.height - 2.4) < 0.05


def test_ladder_portrait_phone_video():
    top = build_ladder(1080, 1920)[0]
    assert (top.name, top.width, top.height) == ("1080p", 1080, 1920)


def test_ladder_tiny_source():
    [only] = build_ladder(160, 120)
    assert (only.width, only.height) == (160, 120)


# ----------------------------------------------------------------- probe
def test_parse_probe_handles_rotation_and_audio():
    info = parse_probe({
        "format": {"duration": "12.5"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
             "avg_frame_rate": "30000/1001", "side_data_list": [{"rotation": -90}]},
            {"codec_type": "audio"},
        ],
    })
    assert (info.width, info.height, info.has_audio) == (1080, 1920, True)
    assert round(info.fps, 2) == 29.97


@pytest.mark.parametrize("data", [{"streams": [{"codec_type": "audio"}]},
                                  {"streams": [{"codec_type": "video", "width": 0, "height": 0}]}])
def test_parse_probe_rejects_bad_input(data):
    with pytest.raises(MediaError):
        parse_probe(data)


# ------------------------------------------------------------ transcode
def test_hls_command_aligns_keyframes_and_maps_streams():
    info = MediaInfo(10, 1280, 720, 30, True, "h264")
    cmd = " ".join(build_hls_command("in.mp4", "/o", info, build_ladder(1280, 720)))
    assert "split=4" in cmd and "-sc_threshold 0" in cmd
    assert "v:0,a:0,name:720p" in cmd and "-master_pl_name master.m3u8" in cmd
    silent_info = MediaInfo(10, 1280, 720, 30, False, "h264")
    silent = " ".join(build_hls_command("in.mp4", "/o", silent_info, build_ladder(1280, 720)))
    assert "0:a:0" not in silent and "v:0,name:720p" in silent


def test_sprite_plan_caps_thumbnails():
    interval, count, w, h = sprite_plan(MediaInfo(3600, 1920, 1080, 30, True, "h264"))
    assert count <= 100 and (w, h) == (160, 90) and interval == 36


def test_vtt_timestamps():
    assert _ts(3725.5) == "01:02:05.500"


# ---------------------------------------------------- real ffmpeg, end to end
def _make_sample(path: Path, seconds=6, size="640x360", audio=True):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)


def _upload_real_video(client, auth, storage, path: Path) -> str:
    data = path.read_bytes()
    plan = client.post("/api/v1/uploads", headers=auth, json={
        "filename": path.name, "content_type": "video/mp4", "size": len(data), "title": "Sample"}).get_json()
    video = db.session.get(Video, plan["video_id"])
    for n in range(1, video.part_count + 1):
        storage.client.upload_part(Bucket=storage.raw_bucket, Key=video.raw_key, UploadId=video.upload_id,
                                   PartNumber=n, Body=data[(n - 1) * video.part_size: n * video.part_size])
    resp = client.post(f"/api/v1/uploads/{video.id}/complete", headers=auth)
    assert resp.status_code == 202
    return video.id


@needs_ffmpeg
def test_upload_to_playable_hls(client, auth, storage, tmp_path):
    sample = tmp_path / "sample.mp4"
    _make_sample(sample)
    vid = _upload_real_video(client, auth, storage, sample)

    video = client.get(f"/api/v1/videos/{vid}", headers=auth).get_json()["video"]
    assert video["status"] == VideoStatus.READY, video.get("error")
    assert [r["name"] for r in video["renditions"]] == ["360p", "240p"]
    assert 5.5 < video["duration_s"] < 6.5

    keys = set(storage.iter_keys(storage.media_bucket, f"hls/{vid}/"))
    for expected in ("master.m3u8", "360p/index.m3u8", "240p/index.m3u8", "poster.jpg", "sprite.jpg",
                     "thumbnails.vtt"):
        assert f"hls/{vid}/{expected}" in keys
    assert any(k.endswith(".ts") for k in keys)

    master = storage.client.get_object(Bucket=storage.media_bucket, Key=f"hls/{vid}/master.m3u8")
    body = master["Body"].read().decode()
    assert body.count("#EXT-X-STREAM-INF") == 2 and "RESOLUTION=640x360" in body
    seg = next(k for k in keys if k.endswith(".ts"))
    head = storage.client.head_object(Bucket=storage.media_bucket, Key=seg)
    assert "immutable" in head["CacheControl"] and head["ContentType"] == "video/mp2t"


@needs_ffmpeg
def test_silent_video_and_retranscode(client, auth, storage, tmp_path):
    sample = tmp_path / "silent.mp4"
    _make_sample(sample, seconds=3, size="320x240", audio=False)
    vid = _upload_real_video(client, auth, storage, sample)
    assert client.get(f"/api/v1/videos/{vid}", headers=auth).get_json()["video"]["status"] == "ready"
    r = client.post(f"/api/v1/videos/{vid}/retranscode", headers=auth)
    assert r.status_code == 202 and r.get_json()["video"]["status"] == "ready"


def test_garbage_upload_fails_cleanly(client, auth, storage):
    plan = client.post("/api/v1/uploads", headers=auth, json={
        "filename": "x.mp4", "content_type": "video/mp4", "size": 1000}).get_json()
    video = db.session.get(Video, plan["video_id"])
    storage.client.upload_part(Bucket=storage.raw_bucket, Key=video.raw_key, UploadId=video.upload_id,
                               PartNumber=1, Body=b"\0" * 1000)
    client.post(f"/api/v1/uploads/{video.id}/complete", headers=auth)
    data = client.get(f"/api/v1/videos/{video.id}", headers=auth).get_json()["video"]
    assert data["status"] == "failed" and data["error"]
