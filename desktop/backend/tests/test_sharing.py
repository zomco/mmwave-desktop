from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tracecue_desktop import sharing


def test_lan_share_serves_only_token_scoped_page_and_bounded_video(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sharing, "_private_route_address", lambda _target: "127.0.0.1")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0123456789" * 100)
    server = sharing.LanClipShareServer()
    try:
        created = server.create_share(
            clip_id="clip_fixture",
            path=clip,
            title="Front door",
            route_target="192.0.2.10",
        )
        with urlopen(created["url"], timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "Front door" in page
            assert "video.mp4" in page
        video_url = created["url"] + "/video.mp4"
        with urlopen(Request(video_url, headers={"Range": "bytes=10-19"}), timeout=5) as response:
            assert response.status == 206
            assert response.read() == b"0123456789"
            assert response.headers["Content-Range"] == "bytes 10-19/1000"
        with pytest.raises(HTTPError) as missing:
            urlopen(created["url"].replace("/s/", "/s/wrong-"), timeout=5)
        assert missing.value.code == 404
    finally:
        server.stop()
