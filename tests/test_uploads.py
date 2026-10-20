from urllib.parse import parse_qs, urlparse

import pytest

from streamforge.api.uploads import S3_MAX_PARTS, S3_MIN_PART, plan_parts
from streamforge.extensions import db
from streamforge.models import Video, VideoStatus

MB = 1024 * 1024


@pytest.mark.parametrize(
    "size,preferred,expect_parts",
    [(1, 8 * MB, 1), (8 * MB, 8 * MB, 1), (8 * MB + 1, 8 * MB, 2), (100 * MB, 1 * MB, 20)],
)
def test_plan_parts(size, preferred, expect_parts):
    part_size, count = plan_parts(size, preferred)
    assert part_size >= S3_MIN_PART
    assert count == expect_parts


def test_plan_parts_respects_s3_part_limit():
    part_size, count = plan_parts(200 * 1024**3, 8 * MB)  # 200 GB
    assert count <= S3_MAX_PARTS
    assert part_size * count >= 200 * 1024**3


def _init(client, auth, size, **extra):
    body = {"filename": "clip.mp4", "content_type": "video/mp4", "size": size, "title": "My clip"}
    body.update(extra)
    return client.post("/api/v1/uploads", json=body, headers=auth)


def _put_parts(storage, video, payload: bytes):
    for n in range(1, video.part_count + 1):
        chunk = payload[(n - 1) * video.part_size : n * video.part_size]
        storage.client.upload_part(
            Bucket=storage.raw_bucket, Key=video.raw_key, UploadId=video.upload_id,
            PartNumber=n, Body=chunk,
        )


def test_full_multipart_flow(client, auth, storage):
    payload = b"x" * (5 * MB) + b"y" * 1234  # two parts
    r = _init(client, auth, len(payload))
    assert r.status_code == 201
    plan = r.get_json()
    assert plan["part_count"] == 2

    # sign a batch of part URLs
    r = client.post(f"/api/v1/uploads/{plan['video_id']}/parts", json={"part_numbers": [1, 2]}, headers=auth)
    urls = r.get_json()["urls"]
    query = parse_qs(urlparse(urls["1"]).query)
    assert query["partNumber"] == ["1"] and "uploadId" in query and "X-Amz-Signature" in query

    video = db.session.get(Video, plan["video_id"])
    # completing early reports exactly which parts are missing
    r = client.post(f"/api/v1/uploads/{video.id}/complete", headers=auth)
    assert r.status_code == 409 and r.get_json()["error"]["details"]["missing"] == [1, 2]

    _put_parts(storage, video, payload)
    status = client.get(f"/api/v1/uploads/{video.id}", headers=auth).get_json()
    assert status["uploaded_parts"] == [1, 2]

    r = client.post(f"/api/v1/uploads/{video.id}/complete", headers=auth)
    assert r.status_code == 202
    assert r.get_json()["video"]["status"] in {VideoStatus.QUEUED, VideoStatus.FAILED, VideoStatus.READY}
    assert storage.object_size(storage.raw_bucket, video.raw_key) == len(payload)


def test_complete_rejects_size_mismatch(client, auth, storage):
    r = _init(client, auth, 10)
    video = db.session.get(Video, r.get_json()["video_id"])
    _put_parts(storage, video, b"123")  # only 3 bytes of a declared 10
    r = client.post(f"/api/v1/uploads/{video.id}/complete", headers=auth)
    assert r.get_json()["error"]["code"] == "size_mismatch"


def test_upload_validation(client, auth):
    assert _init(client, auth, 100, content_type="application/pdf").status_code == 415
    assert _init(client, auth, 0).status_code == 413
    assert _init(client, auth, 100, visibility="secret").status_code == 422
    assert client.post("/api/v1/uploads", json={}).status_code == 401


def test_sign_parts_bounds(client, auth):
    vid = _init(client, auth, 100).get_json()["video_id"]
    for bad in ([0], [2], [], list(range(1, 200)), ["a"]):
        r = client.post(f"/api/v1/uploads/{vid}/parts", json={"part_numbers": bad}, headers=auth)
        assert r.status_code == 422, bad


def test_other_users_cannot_touch_upload(client, auth, register):
    vid = _init(client, auth, 100).get_json()["video_id"]
    other = {"Authorization": f"Bearer {register(email='eve@example.com')}"}
    assert client.get(f"/api/v1/uploads/{vid}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/uploads/{vid}", headers=other).status_code == 404


def test_abort(client, auth):
    vid = _init(client, auth, 100).get_json()["video_id"]
    assert client.delete(f"/api/v1/uploads/{vid}", headers=auth).status_code == 204
    assert db.session.get(Video, vid) is None
