from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracecue_desktop.app import create_app
from tracecue_desktop.services import clamp_candidate_window


ROOT = Path(__file__).resolve().parents[3]
TIMELINE = ROOT / "contracts" / "timeline" / "v1" / "examples" / "minimal.json"


def client(services) -> TestClient:
    return TestClient(create_app(services.config, services=services, start_worker=False))


def test_status_reports_schema_and_media_without_paths(services) -> None:
    response = client(services).get("/api/v1/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 7
    assert payload["bind_host"] == "127.0.0.1"
    assert "data_dir" not in json.dumps(payload)


def test_rejects_cross_origin_browser_request(services) -> None:
    response = client(services).get(
        "/api/v1/status", headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REQUEST_ORIGIN_REJECTED"


def test_event_work_yields_before_queued_camera_refreshes(services, nvr) -> None:
    api = client(services)
    channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    snapshot_job = api.post(f"/api/v1/channels/{channel['id']}/snapshot").json()["job_id"]
    search_job = api.post(
        "/api/v1/search-jobs",
        json={
            "nvr_id": nvr["id"],
            "channel_ids": [channel["id"]],
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "source_modes": ["record_classification"],
            "event_types": ["motion"],
        },
    ).json()["id"]

    assert services.worker.process_once()
    assert api.get(f"/api/v1/jobs/{search_job}").json()["state"] == "succeeded"
    assert api.get(f"/api/v1/jobs/{snapshot_job}").json()["state"] == "queued"


def test_nvr_search_clip_and_bounded_range_workflow(services, nvr) -> None:
    api = client(services)
    channels = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()
    assert len(channels) == 1
    assert channels[0]["id"] != "101"

    details = api.get(f"/api/v1/nvrs/{nvr['id']}/details")
    assert details.status_code == 200
    assert details.json()["nvr"]["encoder_version"] == "fixture-encoder"
    assert details.json()["cameras"][0]["model"] == "fixture-camera"
    assert details.json()["cameras"][0]["channel_id"] == channels[0]["id"]
    assert "password" not in json.dumps(details.json()).lower()

    snapshot = api.post(f"/api/v1/channels/{channels[0]['id']}/snapshot")
    assert snapshot.status_code == 202
    assert services.worker.process_once()
    ready_snapshot = api.get(f"/api/v1/channels/{channels[0]['id']}/snapshot").json()
    assert ready_snapshot["status"] == "ready"
    assert ready_snapshot["stale"] is False
    assert ready_snapshot["refreshing"] is False
    assert api.get(ready_snapshot["content_url"]).content.startswith(b"\xff\xd8\xff")

    services.database.execute(
        "UPDATE channel_snapshots SET expires_ms=0 WHERE channel_id=?",
        (channels[0]["id"],),
    )
    stale_snapshot = api.post(f"/api/v1/channels/{channels[0]['id']}/snapshot").json()
    assert stale_snapshot["status"] == "ready"
    assert stale_snapshot["stale"] is True
    assert stale_snapshot["refreshing"] is True
    assert api.get(stale_snapshot["content_url"]).content.startswith(b"\xff\xd8\xff")
    assert services.worker.process_once()
    refreshed_snapshot = api.get(f"/api/v1/channels/{channels[0]['id']}/snapshot").json()
    assert refreshed_snapshot["status"] == "ready"
    assert refreshed_snapshot["stale"] is False
    assert refreshed_snapshot["refreshing"] is False
    assert refreshed_snapshot["source"] == "live_low_rate"

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
    assert ready_preview["progress"] == 1
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
    assert ready["progress"] == 1
    assert ready["origin"]["bookmark_id"] == bookmarks[0]["id"]
    assert ready["origin"]["search_job_id"] == search.json()["id"]
    assert ready["origin"]["classification"] == "log.hikvision.com/Alarm/motionStart/1"
    assert ready["origin"]["candidate_window_capped"] is True
    assert ready["origin"]["padding_trimmed_for_neighbor_events"] is False
    assert ready["origin"]["time_basis"] == "nvr_index"
    assert ready["requested_window"] == {
        "start_at": "2026-08-12T08:00:00.000Z",
        "end_at": "2026-08-12T08:00:05.000Z",
    }

    share = api.post(f"/api/v1/clips/{ready['id']}/share")
    assert share.status_code == 201
    assert share.json() == {
        "clip_id": ready["id"],
        "url": "http://192.0.2.55:54321/s/fixture-token",
        "expires_at": "2026-08-12T10:01:40.000Z",
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


def test_line_event_visual_analysis_is_cached_as_auxiliary_evidence(services, nvr) -> None:
    api = client(services)
    channel = api.post(f"/api/v1/nvrs/{nvr['id']}/sync-channels").json()[0]
    audit = api.post(f"/api/v1/nvrs/{nvr['id']}/event-audit")
    assert audit.status_code == 200
    assert api.get("/api/v1/status").json()["visual_analysis"]["available"] is True

    search = api.post(
        "/api/v1/search-jobs",
        json={
            "nvr_id": nvr["id"],
            "channel_ids": [channel["id"]],
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "source_modes": ["historical_event_log"],
            "event_types": ["line_crossing"],
        },
    )
    assert search.status_code == 202
    assert services.worker.process_once()
    bookmark = api.get(f"/api/v1/search-jobs/{search.json()['id']}/results").json()["items"][0]
    assert bookmark["visual_analysis"] is None

    requested = api.post(f"/api/v1/bookmarks/{bookmark['id']}/visual-analysis")
    assert requested.status_code == 202
    assert requested.json()["status"] == "queued"
    assert services.worker.process_once()

    ready = api.get(f"/api/v1/bookmarks/{bookmark['id']}/visual-analysis").json()
    assert ready["status"] == "ready"
    assert ready["verdict"] == "confirmed_trigger"
    assert ready["result"]["trigger_at"] == "2026-08-12T08:00:02.000Z"
    assert ready["result"]["evidence_animation_ready"] is True
    assert api.get(ready["evidence_content_url"]).content.startswith(b"RIFF")
    assert api.get(f"/api/v1/bookmarks/{bookmark['id']}").json()["visual_analysis"]["verdict"] == "confirmed_trigger"


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
    assert api.post(
        "/api/v1/trace-sessions",
        json={"channel_ids": [channel["id"]], "event_types": ["motion", "line_crossing"]},
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
    assert summary["timeline"][0]["start_at"] == "2026-08-12T08:00:00.000Z"
    assert summary["timeline"][0]["end_at"] == "2026-08-12T08:00:09.000Z"
    assert summary["timeline"][0]["duration_ms"] == 9000
    assert summary["timeline"][0]["cluster_size"] == 1
    assert summary["timeline_truncated"] is False
    assert summary["activity_counts"] == {"isolated": 1, "clustered": 0}
    assert summary["duration_range"] == {"known_count": 1, "min_ms": 9000, "max_ms": 9000}

    results = api.get(
        f"/api/v1/trace-sessions/{session_id}/results?duration_class=5_to_30s"
    ).json()
    assert results["total"] == 1
    assert results["counts"]["unreviewed"] == 1
    assert results["items"][0]["review_state"] == "unreviewed"
    assert results["timeline"]
    assert results["items"][0]["attributes"]["hikvision"]["event_duration_ms"] == 9000
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?duration_class=unknown"
    ).json()["total"] == 0
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?min_duration_ms=10000"
    ).json()["total"] == 0
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?activity_mode=isolated"
    ).json()["total"] == 1
    bookmark_id = results["items"][0]["id"]

    focused = api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": "2026-08-12T08:00:05Z", "to": "2026-08-12T08:00:08Z"},
    )
    assert focused.status_code == 200
    assert focused.json()["total"] == 1
    assert focused.json()["selected_window"] == {
        "start_at": "2026-08-12T08:00:05.000Z",
        "end_at": "2026-08-12T08:00:08.000Z",
    }
    assert focused.json()["duration_buckets"]["5_to_30s"] == 1
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": "2026-08-12T09:00:00Z", "to": "2026-08-12T10:00:00Z"},
    ).json()["total"] == 0
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"from": "2026-08-12T08:00:00Z"},
    ).status_code == 422
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"min_duration_ms": 10_000, "max_duration_ms": 5_000},
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


def test_trace_secondary_activity_clusters_and_exact_duration_bounds(services, nvr) -> None:
    api = client(services)
    channel = api.get(f"/api/v1/nvrs/{nvr['id']}/channels").json()[0]
    session_id = api.post(
        "/api/v1/trace-sessions",
        json={"channel_ids": [channel["id"]], "event_types": ["motion"]},
    ).json()["id"]
    api.post(
        f"/api/v1/trace-sessions/{session_id}/iterations",
        json={
            "from": "2026-08-12T08:00:00Z",
            "to": "2026-08-12T08:01:00Z",
            "label": "活动模式夹具",
        },
    )
    assert services.worker.process_once()

    original = services.database.one("SELECT * FROM intervals LIMIT 1")
    assert original is not None
    job_id = services.database.one(
        """
        SELECT tij.job_id FROM trace_iterations ti
        JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
        WHERE ti.session_id=?
        """,
        (session_id,),
    )["job_id"]
    columns = list(original)
    for suffix, start_offset, end_offset in (("cluster", 15_000, 20_000), ("isolated", 55_000, 59_000)):
        values = dict(original)
        values["id"] = f"bookmark_{suffix}"
        values["source_event_id"] = f"fixture-event-{suffix}"
        for name in ("raw_start_ms", "resolved_start_ms"):
            values[name] = int(original[name]) + start_offset
        for name in ("raw_end_ms", "resolved_end_ms"):
            values[name] = int(original["raw_start_ms"]) + end_offset
        if original["media_start_ms"] is not None:
            values["media_start_ms"] = int(original["raw_start_ms"]) + start_offset
            values["media_end_ms"] = int(original["raw_start_ms"]) + end_offset
        attributes = json.loads(original["attributes_json"])
        attributes["hikvision"]["event_duration_ms"] = end_offset - start_offset
        values["attributes_json"] = json.dumps(attributes)
        services.database.execute(
            f"INSERT INTO intervals({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(values[column] for column in columns),
        )
        services.database.execute(
            "INSERT INTO search_results(search_job_id, interval_id) VALUES (?, ?)",
            (job_id, values["id"]),
        )

    summary = api.get(
        f"/api/v1/trace-sessions/{session_id}/results?summary_only=true"
    ).json()
    assert summary["activity_cluster_gap_ms"] == 30_000
    assert summary["activity_counts"] == {"isolated": 1, "clustered": 2}
    assert [item["cluster_size"] for item in summary["timeline"]] == [2, 2, 1]
    assert summary["duration_range"] == {"known_count": 3, "min_ms": 4000, "max_ms": 9000}
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?activity_mode=clustered"
    ).json()["total"] == 2
    assert api.get(
        f"/api/v1/trace-sessions/{session_id}/results?activity_mode=isolated"
    ).json()["total"] == 1
    exact = api.get(
        f"/api/v1/trace-sessions/{session_id}/results",
        params={"min_duration_ms": 6_000, "max_duration_ms": 10_000},
    ).json()
    assert exact["total"] == 1
    assert exact["items"][0]["attributes"]["hikvision"]["event_duration_ms"] == 9000


def test_candidate_padding_stops_at_adjacent_event_midpoints_without_trimming_event_bodies() -> None:
    assert clamp_candidate_window(
        33_000, 57_000, 38_000, 47_000, next_event_start_ms=57_000
    ) == (33_000, 52_000, True)
    assert clamp_candidate_window(
        52_000, 76_000, 57_000, 66_000, next_event_start_ms=83_000
    ) == (52_000, 74_000, True)
    assert clamp_candidate_window(
        52_000, 76_000, 57_000, 66_000, previous_event_end_ms=47_000
    ) == (52_000, 76_000, False)
    # A genuinely overlapping event body is not a safe padding boundary.
    assert clamp_candidate_window(
        33_000, 57_000, 38_000, 47_000, next_event_start_ms=45_000
    ) == (33_000, 57_000, False)


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
