import base64
import hashlib
import time
from urllib.parse import parse_qs

import pytest

from streamforge.cdn import edge_token, playback_for, verify_edge_token
from streamforge.models import VideoStatus
from tests.test_videos import make_video

VID = "0b6f1c8e-2f4e-4d47-9a51-3c1f7e0d9a10"


def test_token_matches_nginx_secure_link_format():
    # nginx: secure_link_md5 "$expires$vid $secret" -> base64url(md5), no padding
    expected = base64.urlsafe_b64encode(hashlib.md5(f"1700000000{VID} s3cret".encode()).digest())
    assert edge_token(VID, 1700000000, "s3cret") == expected.decode().rstrip("=")


def test_verify_token():
    exp = int(time.time()) + 60
    tok = edge_token(VID, exp, "k")
    assert verify_edge_token(tok, VID, exp, "k")
    assert not verify_edge_token(tok, VID, exp, "other-secret")
    assert not verify_edge_token(tok, "f" * 36, exp, "k")  # token is bound to one video
    assert not verify_edge_token(tok, VID, exp, "k", now=exp + 1)  # expired


@pytest.fixture
def media(app, storage):
    """A ready video with a few fake HLS assets in the media bucket."""
    video = make_video_with_user(app)
    put = storage.client.put_object
    put(Bucket=storage.media_bucket, Key=f"hls/{video.id}/master.m3u8", Body=b"#EXTM3U\n",
        ContentType="application/vnd.apple.mpegurl", CacheControl="public, max-age=60")
    put(Bucket=storage.media_bucket, Key=f"hls/{video.id}/720p/seg_0000.ts", Body=bytes(range(256)) * 4,
        ContentType="video/mp2t", CacheControl="public, max-age=31536000, immutable")
    return video


def make_video_with_user(app):
    from streamforge.extensions import db
    from streamforge.models import User

    user = User(email="alice@example.com", display_name="Alice")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return make_video(status=VideoStatus.READY)


def test_playback_and_direct_delivery(client, media):
    pb = client.get(f"/api/v1/videos/{media.id}/playback").get_json()["playback"]
    assert pb["hls"].startswith("/cdn/") and pb["hls"].endswith(f"/{media.id}/master.m3u8")

    r = client.get(pb["hls"])
    assert r.status_code == 200 and r.data == b"#EXTM3U\n"
    assert r.headers["Content-Type"] == "application/vnd.apple.mpegurl"

    # segments resolve relative to the playlist and inherit the token
    seg = pb["hls"].replace("master.m3u8", "720p/seg_0000.ts")
    r = client.get(seg, headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.data == bytes(range(10, 20))
    assert "immutable" in r.headers["Cache-Control"]


def test_bad_and_expired_tokens(client, media):
    exp = int(time.time()) + 60
    assert client.get(f"/cdn/forged/{exp}/{media.id}/master.m3u8").status_code == 403
    old = int(time.time()) - 5
    tok = edge_token(media.id, old, "dev-only-cdn-signing-secret")
    assert client.get(f"/cdn/{tok}/{old}/{media.id}/master.m3u8").status_code == 410


def test_path_traversal_and_missing_files(client, media, app):
    exp = int(time.time()) + 60
    tok = edge_token(media.id, exp, app.config["CDN_SIGNING_SECRET"])
    for path in ("../../etc/passwd", "master.m3u8.exe", "nope.ts"):
        assert client.get(f"/cdn/{tok}/{exp}/{media.id}/{path}").status_code == 404


def test_origin_requires_shared_secret(client, media, app):
    app.config["CDN_ORIGIN_SECRET"] = "edge-only"
    url = f"/origin/{media.id}/master.m3u8"
    assert client.get(url).status_code == 403
    assert client.get(url, headers={"X-Origin-Secret": "wrong"}).status_code == 403
    assert client.get(url, headers={"X-Origin-Secret": "edge-only"}).status_code == 200


def test_playback_requires_ready(client, auth):
    video = make_video(status=VideoStatus.PROCESSING)
    r = client.get(f"/api/v1/videos/{video.id}/playback", headers=auth)
    assert r.status_code == 409


def test_library_items_carry_poster(client, media):
    item = client.get("/api/v1/videos").get_json()["items"][0]
    assert item["poster_url"].endswith("/poster.jpg")


def test_cloudfront_signed_urls(app):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app.config.update(
        CDN_MODE="cloudfront", CDN_BASE_URL="https://d111.cloudfront.net", CLOUDFRONT_KEY_PAIR_ID="K2TESTKEY",
        CLOUDFRONT_PRIVATE_KEY=key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    )
    pb = playback_for(VID)
    assert pb.hls.startswith(f"https://d111.cloudfront.net/hls/{VID}/master.m3u8?")
    q = {k: v[0] for k, v in parse_qs(pb.query).items()}
    assert q["Key-Pair-Id"] == "K2TESTKEY"

    def cf_b64decode(s: str) -> bytes:  # CloudFront's URL-safe base64 variant
        return base64.b64decode(s.replace("-", "+").replace("_", "=").replace("~", "/"))

    policy = cf_b64decode(q["Policy"])
    assert f"hls/{VID}/*".encode() in policy  # one wildcard signature covers every segment
    key.public_key().verify(cf_b64decode(q["Signature"]), policy, padding.PKCS1v15(), hashes.SHA1())
