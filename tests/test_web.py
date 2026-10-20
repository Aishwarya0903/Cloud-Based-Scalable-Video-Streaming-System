import pytest


@pytest.mark.parametrize("path", ["/", "/upload", "/studio", "/login", "/watch/0b6f1c8e-2f4e-4d47-9a51-3c1f7e0d9a10"])
def test_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert b"/assets/css/app.css" in r.data and b"StreamForge" in r.data


def test_assets_served(client):
    for asset in ("css/app.css", "js/api.js", "js/watch.js", "js/upload.js", "vendor/hls-1.5.20.min.js"):
        assert client.get(f"/assets/{asset}").status_code == 200, asset


def test_watch_page_loads_player(client):
    html = client.get("/watch/abc").data
    assert b"hls-1.5.20.min.js" in html and b'id="ladder"' in html
