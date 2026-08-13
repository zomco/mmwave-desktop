from __future__ import annotations

import json
from pathlib import Path

import pytest
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
    assert payload["schema_version"] == 5
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

    snapshot = api.post(f"/api/v1/channels/{channels[0]['id']}/snapshot")
    assert snapshot.status_code == 202
    assert services.worker.process_once()
    ready_snapshot = api.get(f"/api/v1/channels/{channels[0]['id']}/snapshot").json()
    assert ready_snapshot["status"] == "ready"
    assert api.get(ready_snapshot["content_url"]).content.startswith(b"\xff\xd8\xff")

    search = api.post(
        "/api/v1/search-jobs",
        json={
            "nvr_id": nvr["id"],
            "channel_ids": [channels[0]["id"]],
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "source_modes": ["record_classification"],
            "event_types": ["motion"],
        },
    )
    assert search.status_code == 202
    assert services.worker.process_once()
    finished = api.get(f"/api/v1/jobs/{search.json()['id']}").json()
    assert finished["state"] == "succeeded"
    search_results = api.get(f"/api/v1/search-jobs/{search.json()['id']}/results").json()
    assert len(search_results["items"]) == 1
    assert search_results["total"] == 1

    bookmarks = api.get("/api/v1/bookmarks").json()["items"]
    assert len(bookmarks) == 1
    assert bookmarks[0]["quality"]["gate"] == "unknown"
    assert "nvr_originated" in bookmarks[0]["tags"]

    preview = api.post(f"/api/v1/bookmarks/{bookmarks[0]['id']}/preview")
    assert preview.status_code == 202
    assert services.worker.process_once()
    ready_preview = api.get(f"/api/v1/bookmarks/{bookmarks[0]['id']}/preview").json()
    assert ready_preview["status"] == "ready"
    assert api.get(ready_preview["content_url"]).content.startswith(b"\xff\xd8\xff")

    animation = api.post(f"/api/v1/bookmarks/{bookmarks[0]['id']}/animation")
    assert animation.status_code == 202
    assert services.worker.process_once()
    ready_animation = api.get(f"/api/v1/bookmarks/{bookmarks[0]['id']}/animation").json()
    assert ready_animation["status"] == "ready"
    assert api.get(ready_animation["content_url"]).headers["content-type"].startswith("image/webp")

    clip = api.post(
        "/api/v1/clips",
        json={
            "bookmark_id": bookmarks[0]["id"],
            "window_override": {"pre_roll_ms": 0, "post_roll_ms": 0, "max_duration_ms": 5000},
            "audio_policy": "prefer",
        },
    )
    assert clip.status_code == 202
    assert services.worker.process_once()
    ready = api.get(f"/api/v1/clips/{clip.json()['id']}").json()
    assert ready["status"] == "ready"
    assert ready["origin"]["bookmark_id"] == bookmarks[0]["id"]
    assert ready["origin"]["search_job_id"] == search.json()["id"]
    assert ready["origin"]["classification"] == "log.hikvision.com/Alarm/motionStart/1"
    assert ready["origin"]["candidate_window_capped"] is True
    assert ready["origin"]["time_basis"] == "nvr_index"
    assert ready["requested_window"] == {
        "start_at": "2026-08-12T08:00:00.000Z",
        "end_at": "2026-08-12T08:00:05.000Z",
    }

    ranged = api.get(ready["content_url"], headers={"Range": "bytes=10-19"})
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"
    assert ranged.headers["content-range"].endswith("/1000")

    invalid = api.get(ready["content_url"], headers={"Range": "bytes=1000-1001"})
    assert invalid.status_code == 416


def test_device_discovery_event_audit_and_saved_area_filter(services, nvr) -> None:
    api = client(services)
    discovered = api.post("/api/v1/nvrs/discover", json={"timeout_seconds": 1}).json()
    assert discovered == [
        {
            "host": "192.0.2.20",
            "http_port": 80,
            "use_https": False,
            "name": "Discovered recorder",
            "model": "fixture-discovery",
            "device_types": ["NetworkVideoTransmitter"],
            "discovery_protocol": "onvif_ws_discovery",
            "already_added": False,
        }
    ]

    audit = api.post(f"/api/v1/nvrs/{nvr['id']}/event-audit").json()
    assert audit["schema_version"] == 4
    assert audit["rules"][0]["enabled"] is True
    assert audit["rules"][0]["channel_label"] == "Front door"
    assert api.get(f"/api/v1/nvrs/{nvr['id']}/event-audit").json() == audit

    channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    preset = api.post(
        "/api/v1/search-presets",
        json={
            "name": "Front entrance motion",
            "nvr_id": nvr["id"],
            "area_name": "Front entrance",
            "channel_ids": [channel["id"]],
            "event_types": ["motion"],
        },
    )
    assert preset.status_code == 201
    assert api.get("/api/v1/search-presets").json()[0]["area_name"] == "Front entrance"
    assert api.delete(f"/api/v1/search-presets/{preset.json()['id']}").status_code == 204


def test_continuous_and_catch_all_smart_are_not_event_filters(services, nvr) -> None:
    api = client(services)
    channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    for event_type in ("continuous", "smart"):
        response = api.post(
            "/api/v1/trace-sessions",
            json={"channel_ids": [channel["id"]], "event_types": [event_type]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert api.post(
        "/api/v1/trace-sessions",
        json={"channel_ids": [channel["id"]], "event_types": []},
    ).status_code == 422
    assert api.post(
        "/api/v1/trace-sessions",
        json={"channel_ids": [channel["id"], channel["id"]], "event_types": ["motion"]},
    ).status_code == 422


def test_trace_session_uses_one_window_then_exposes_secondary_facets_and_reviews(
    services, nvr
) -> None:
    api = client(services)
    channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    session_response = api.post(
        "/api/v1/trace-sessions",
        json={"channel_ids": [channel["id"]], "event_types": ["motion"]},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    first = api.post(
        f"/api/v1/trace-sessions/{session_id}/iterations",
        json={
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "label": "昨晚",
        },
    )
    assert first.status_code == 202
    assert services.worker.process_once()

    second = api.post(
        f"/api/v1/trace-sessions/{session_id}/iterations",
        json={
            "from": "2026-08-11T08:00:00Z",
            "to": "2026-08-11T08:01:00Z",
            "label": "前一晚",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "TRACE_SESSION_WINDOW_FIXED"
    restored = api.get(f"/api/v1/trace-sessions/{session_id}").json()
    assert len(restored["iterations"]) == 1
    assert restored["result_count"] == 1
    assert api.get("/api/v1/trace-sessions?limit=1").json()[0]["id"] == session_id

    summary = api.get(
        f"/api/v1/trace-sessions/{session_id}/results?summary_only=true"
    ).json()
    assert summary["items"] == []
    assert summary["summary_only"] is True
    assert summary["duration_buckets"]["5_to_30s"] == 1
    assert summary["duration_buckets"]["unknown"] == 0
    assert summary["event_type_counts"]["motion"] == 1
    assert summary["density"][0]["end_at"] == "2026-08-12T09:00:00.000Z"

    results = api.get(
        f"/api/v1/trace-sessions/{session_id}/results?duration_class=5_to_30s"
    ).json()
    assert results["total"] == 1
    assert results["counts"]["unreviewed"] == 1
    assert results["items"][0]["review_state"] == "unreviewed"
    assert results["density"]
    assert results["items"][0]["attributes"]["hikvision"]["event_duration_ms"] == 9000
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?duration_class=unknown"
    ).json()["total"] == 0
    bookmark_id = results["items"][0]["id"]

    focused = api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": results["density"][0]["start_at"], "to": "2026-08-12T09:00:00Z"},
    )
    assert focused.status_code == 200
    assert focused.json()["total"] == 1
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": "2026-08-12T09:00:00Z", "to": "2026-08-12T10:00:00Z"},
    ).json()["total"] == 0
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": "2026-08-12T08:00:00Z"},
    ).status_code == 422

    reviewed = api.patch(
        f"/api/v1/trace-sessions/{session_id}/events/{bookmark_id}",
        json={"state": "excluded"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["state"] == "excluded"
    assert api.get(f"/api/v1/trace-sessions/{session_id}/results").json()["total"] == 0
    excluded = api.get(
        f"/api/v1/trace-sessions/{session_id}/results?review_state=excluded"
    ).json()
    assert excluded["total"] == 1
    assert excluded["items"][0]["review_state"] == "excluded"

    assert api.delete(f"/api/v1/trace-sessions/{session_id}").status_code == 204
    assert api.get(f"/api/v1/trace-sessions/{session_id}").status_code == 404


def test_delete_nvr_removes_local_credentials_and_indexed_sources(services, nvr) -> None:
    api = client(services)
    nvr_row = services.database.one("SELECT secret_ref FROM nvrs WHERE id=?", (nvr["id"],))
    channels = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()
    search = api.post(
        "/api/v1/search-jobs",
        json={
            "nvr_id": nvr["id"],
            "channel_ids": [channels[0]["id"]],
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "event_types": ["motion"],
        },
    )
    assert search.status_code == 202
    assert services.worker.process_once()
    assert api.get("/api/v1/sources").json()

    deleted = api.delete(f"/api/v1/nvrs/{nvr['id']}")

    assert deleted.status_code == 204
    assert api.get("/api/v1/nvrs").json() == []
    assert api.get("/api/v1/sources").json() == []
    assert api.get("/api/v1/source-channels").json() == []
    assert api.get("/api/v1/bookmarks").json()["items"] == []
    with pytest.raises(KeyError):
        services.secret_store.get(nvr_row["secret_ref"])


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
