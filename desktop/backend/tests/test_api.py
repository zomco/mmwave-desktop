from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tracecue_desktop.app import create_app


ROOT = Path(__file__).resolve().parents[3]
TIMELINE = ROOT / "contracts" / "timeline" / "v1" / "examples" / "minimal.json"


def client(services) -> TestClient:
    return TestClient(create_app(services.config, services=services, start_worker=False))


def test_status_reports_schema_and_media_without_paths(services) -> None:
    response = client(services).get("/api/v1/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["bind_host"] == "127.0.0.1"
    assert "data_dir" not in json.dumps(payload)


def test_rejects_cross_origin_browser_request(services) -> None:
    response = client(services).get(
        "/api/v1/status", headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REQUEST_ORIGIN_REJECTED"


def test_nvr_search_clip_and_bounded_range_workflow(services, nvr) -> None:
    api = client(services)
    channels = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()
    assert len(channels) == 1
    assert channels[0]["id"] != "101"

    search = api.post(
        "/api/v1/search-jobs",
        json={
            "nvr_id": nvr["id"],
            "channel_ids": [channels[0]["id"]],
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "source_modes": ["record_classification"],
        },
    )
    assert search.status_code == 202
    assert services.worker.process_once()
    finished = api.get(f"/api/v1/jobs/{search.json()['id']}").json()
    assert finished["state"] == "succeeded"

    bookmarks = api.get("/api/v1/bookmarks").json()["items"]
    assert len(bookmarks) == 1
    assert bookmarks[0]["quality"]["gate"] == "unknown"
    assert "nvr_originated" in bookmarks[0]["tags"]

    clip = api.post(
        "/api/v1/clips",
        json={
            "bookmark_id": bookmarks[0]["id"],
            "window_override": {"pre_roll_ms": 0, "post_roll_ms": 0},
            "audio_policy": "prefer",
        },
    )
    assert clip.status_code == 202
    assert services.worker.process_once()
    ready = api.get(f"/api/v1/clips/{clip.json()['id']}").json()
    assert ready["status"] == "ready"

    ranged = api.get(ready["content_url"], headers={"Range": "bytes=10-19"})
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"
    assert ranged.headers["content-range"].endswith("/1000")

    invalid = api.get(ready["content_url"], headers={"Range": "bytes=1000-1001"})
    assert invalid.status_code == 416


def test_timeline_inspect_commit_mapping_and_idempotency(services, nvr) -> None:
    api = client(services)
    inspected = api.post(
        "/api/v1/timeline-imports/inspect",
        content=TIMELINE.read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    assert inspected.status_code == 201
    assert inspected.json()["diagnostics"]["interval_count"] == 1
    assert api.get("/api/v1/bookmarks").json()["items"] == []

    import_id = inspected.json()["id"]
    content_hash = inspected.json()["content_hash"]
    first = api.post(
        f"/api/v1/timeline-imports/{import_id}/commit",
        json={"content_hash": content_hash},
    )
    second = api.post(f"/api/v1/timeline-imports/{import_id}/commit", json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "committed"
    assert len(api.get("/api/v1/bookmarks").json()["items"]) == 1

    source_channel = api.get("/api/v1/source-channels").json()[0]
    nvr_channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    mapped = api.put(
        f"/api/v1/source-channels/{source_channel['id']}/binding",
        json={
            "space_name": "East hallway",
            "nvr_channel_id": nvr_channel["id"],
            "clock_correction_ms": 1000,
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["clock_correction_ms"] == 1000
    bookmark = api.get("/api/v1/bookmarks").json()["items"][0]
    assert bookmark["clock_correction_ms"] == 1000
    assert bookmark["start_at"] == "2026-08-12T08:12:04.240Z"


def test_error_envelope_is_stable_and_safe(services) -> None:
    response = client(services).get("/api/v1/nvrs/missing")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NVR_NOT_FOUND"
    assert error["request_id"].startswith("req_")
    assert "Traceback" not in json.dumps(error)


def test_diagnostics_bundle_redacts_addresses_credentials_and_locators(services, nvr) -> None:
    response = client(services).get("/api/v1/diagnostics/export")
    assert response.status_code == 200
    raw = response.content
    assert b"192.0.2.10" not in raw
    assert b"fixture-user" not in raw
    assert b"secret-password" not in raw
    assert b"rtsp://" not in raw
    assert response.headers["content-disposition"].endswith('tracecue-diagnostics.json"')


def test_diagnostics_bundle_redacts_addresses_credentials_and_locators(services, nvr) -> None:
    response = client(services).get("/api/v1/diagnostics/export")
    assert response.status_code == 200
    raw = response.content
    assert b"192.0.2.10" not in raw
    assert b"fixture-user" not in raw
    assert b"secret-password" not in raw
    assert b"rtsp://" not in raw
    assert response.headers["content-disposition"].endswith('tracecue-diagnostics.json"')
