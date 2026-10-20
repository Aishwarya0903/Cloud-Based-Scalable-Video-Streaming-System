from streamforge.extensions import db
from streamforge.models import User, Video, VideoStatus, Visibility


def make_video(owner_email="alice@example.com", **kw) -> Video:
    owner = db.session.query(User).filter_by(email=owner_email).one()
    fields = dict(
        owner_id=owner.id, title="Clip", original_filename="c.mp4", content_type="video/mp4",
        size_bytes=1, raw_key="uploads/x.mp4", part_size=1, part_count=1,
        status=VideoStatus.READY, visibility=Visibility.PUBLIC,
    )
    fields.update(kw)
    video = Video(**fields)
    db.session.add(video)
    db.session.commit()
    return video


def test_library_only_lists_public_ready(client, auth):
    make_video(title="Ocean waves")
    make_video(title="Draft", status=VideoStatus.PROCESSING)
    make_video(title="Secret", visibility=Visibility.PRIVATE)
    make_video(title="Link only", visibility=Visibility.UNLISTED)
    data = client.get("/api/v1/videos").get_json()
    assert [v["title"] for v in data["items"]] == ["Ocean waves"]
    assert client.get("/api/v1/videos?q=ocean").get_json()["total"] == 1
    assert client.get("/api/v1/videos?q=zzz").get_json()["total"] == 0
    assert client.get("/api/v1/videos?sort=bogus").status_code == 422


def test_my_videos_shows_everything(client, auth):
    make_video(title="A")
    make_video(title="B", status=VideoStatus.FAILED, visibility=Visibility.PRIVATE)
    data = client.get("/api/v1/me/videos", headers=auth).get_json()
    assert data["total"] == 2
    assert "size_bytes" in data["items"][0]


def test_private_video_access(client, auth, register):
    v = make_video(visibility=Visibility.PRIVATE)
    assert client.get(f"/api/v1/videos/{v.id}").status_code == 404
    assert client.get(f"/api/v1/videos/{v.id}", headers=auth).status_code == 200
    unlisted = make_video(visibility=Visibility.UNLISTED)
    assert client.get(f"/api/v1/videos/{unlisted.id}").status_code == 200


def test_update_and_delete_owner_only(client, auth, register):
    v = make_video()
    other = {"Authorization": f"Bearer {register(email='eve@example.com')}"}
    assert client.patch(f"/api/v1/videos/{v.id}", json={"title": "x"}, headers=other).status_code == 403
    r = client.patch(f"/api/v1/videos/{v.id}", json={"title": "Renamed", "visibility": "unlisted"}, headers=auth)
    assert r.get_json()["video"]["title"] == "Renamed"
    assert client.patch(f"/api/v1/videos/{v.id}", json={"visibility": "nope"}, headers=auth).status_code == 422
    assert client.delete(f"/api/v1/videos/{v.id}", headers=other).status_code == 403
    assert client.delete(f"/api/v1/videos/{v.id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/videos/{v.id}", headers=auth).status_code == 404
