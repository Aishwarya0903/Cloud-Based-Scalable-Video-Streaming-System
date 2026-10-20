import uuid
from datetime import timedelta

from streamforge.api.analytics import _mask
from streamforge.extensions import db
from streamforge.models import PlaybackSession, VideoStatus, utcnow
from tests.test_videos import make_video


def sid():
    return str(uuid.uuid4())


def send(client, vid, **event):
    return client.post(f"/api/v1/videos/{vid}/events", json=event)


def test_mask_covers_slices():
    assert _mask(0, 0, 100) == 1
    assert _mask(0, 100, 100) == (1 << 20) - 1
    assert _mask(50, 59, 100) == (1 << 10) | (1 << 11)


def test_session_lifecycle_and_stats(client, auth):
    v = make_video(duration_s=100.0)
    s1, s2 = sid(), sid()
    assert send(client, v.id, type="start", session_id=s1, startup_ms=400, position=0).status_code == 204
    for pos in range(10, 101, 10):  # watches the whole thing, one stall
        send(client, v.id, type="heartbeat", session_id=s1, watch_delta=10, from_position=pos - 10,
             position=pos, bitrate=3_000_000, rebuffer_ms_delta=500 if pos == 50 else 0,
             rebuffer_count_delta=1 if pos == 50 else 0, switches_delta=1 if pos == 20 else 0)
    send(client, v.id, type="start", session_id=s2, startup_ms=1200, position=0)
    send(client, v.id, type="heartbeat", session_id=s2, watch_delta=25, from_position=0, position=25,
         bitrate=1_000_000)
    send(client, v.id, type="end", session_id=s2, position=25)

    stats = client.get(f"/api/v1/videos/{v.id}/stats", headers=auth).get_json()["stats"]
    assert stats["views"] == 2
    assert stats["completion_rate"] == 50.0
    assert stats["watch_time_seconds"] == 125.0
    assert stats["startup_ms_p50"] == 800.0
    assert stats["rebuffer_ratio"] == round(0.5 / 125.5 * 100, 2)
    assert stats["sessions_with_stalls"] == 50.0
    assert stats["avg_bitrate_bps"] == round((3e6 * 100 + 1e6 * 25) / 125)
    assert stats["retention"][0] == 100.0 and stats["retention"][-1] == 50.0
    assert client.get(f"/api/v1/videos/{v.id}", headers=auth).get_json()["video"]["view_count"] == 2


def test_events_are_validated_and_clamped(client, auth):
    v = make_video(duration_s=60.0)
    assert send(client, v.id, type="explode", session_id=sid()).status_code == 422
    assert send(client, v.id, type="start", session_id="../../x").status_code == 422
    assert send(client, "f" * 36, type="start", session_id=sid()).status_code == 404
    s = sid()
    send(client, v.id, type="start", session_id=s)
    send(client, v.id, type="heartbeat", session_id=s, watch_delta=1e9, position=1e9, bitrate="nan")
    row = db.session.get(PlaybackSession, s)
    assert row.watch_seconds == 60 and row.completed
    # heartbeat for a session we never saw start is ignored, not counted as a view
    assert send(client, v.id, type="heartbeat", session_id=sid(), watch_delta=5).status_code == 204
    assert db.session.query(PlaybackSession).count() == 1


def test_sendbeacon_text_plain_body(client, auth):
    v = make_video(duration_s=10.0)
    r = client.post(f"/api/v1/videos/{v.id}/events", data=f'{{"type":"start","session_id":"{sid()}"}}',
                    content_type="text/plain;charset=UTF-8")
    assert r.status_code == 204


def test_stats_are_owner_only(client, auth, register):
    v = make_video(duration_s=10.0)
    other = {"Authorization": f"Bearer {register(email='eve@example.com')}"}
    assert client.get(f"/api/v1/videos/{v.id}/stats", headers=other).status_code == 404


def test_trending_prefers_recent_engaged_views(client, auth):
    old_hit, fresh, unwatched = (make_video(title=t, duration_s=100.0) for t in ("old", "fresh", "none"))
    hidden = make_video(title="private", duration_s=100.0, visibility="private")
    now = utcnow()
    for _ in range(6):  # six long views, 60 hours ago
        db.session.add(PlaybackSession(id=sid(), video_id=old_hit.id, started_at=now - timedelta(hours=60),
                                       watch_seconds=300))
    for _ in range(3):
        db.session.add(PlaybackSession(id=sid(), video_id=fresh.id, started_at=now, watch_seconds=300))
    db.session.add(PlaybackSession(id=sid(), video_id=hidden.id, started_at=now, watch_seconds=600))
    db.session.commit()
    items = client.get("/api/v1/trending").get_json()["items"]
    assert [i["title"] for i in items] == ["fresh", "old"]
    assert items[0]["poster_url"].endswith("poster.jpg")
    assert unwatched.status == VideoStatus.READY


def test_deleting_video_removes_sessions(client, auth):
    v = make_video(duration_s=10.0)
    send(client, v.id, type="start", session_id=sid())
    client.delete(f"/api/v1/videos/{v.id}", headers=auth)
    assert db.session.query(PlaybackSession).count() == 0
