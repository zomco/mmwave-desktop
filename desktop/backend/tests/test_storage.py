from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tracecue_desktop.database import Database
from tracecue_desktop.secrets import WindowsDpapiSecretStore
from tracecue_desktop.services import now_ms


def test_running_jobs_become_interrupted_on_restart(tmp_path: Path) -> None:
    path = tmp_path / "restart.sqlite"
    database = Database(path)
    timestamp = now_ms()
    database.initialize(timestamp)
    database.execute(
        """
        INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms)
        VALUES ('job_restart', 'fixture', 'running', '{}', 1, ?, ?)
        """,
        (timestamp, timestamp),
    )
    Database(path).initialize(timestamp + 1)
    row = database.one("SELECT state, error_code FROM jobs WHERE id='job_restart'")
    assert row == {"state": "interrupted", "error_code": "JOB_INTERRUPTED"}


def test_interrupted_clip_is_not_left_generating(tmp_path: Path) -> None:
    database = Database(tmp_path / "tracecue.sqlite")
    database.initialize(100)
    database.execute(
        "INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms) "
        "VALUES ('job_1', 'clip', 'running', '{}', 1, 100, 100)"
    )
    database.execute(
        "INSERT INTO nvrs(id, name, host, http_port, use_https, verify_tls, secret_ref, created_ms, updated_ms) "
        "VALUES ('nvr_1', 'test', '192.0.2.1', 80, 0, 1, 'secret_1', 100, 100)"
    )
    database.execute(
        "INSERT INTO nvr_channels(id, nvr_id, external_channel_id, metadata_json, device_name, "
        "online, created_ms, updated_ms) VALUES "
        "('channel_1', 'nvr_1', '1', '{}', 'Channel 1', 1, 100, 100)"
    )
    database.execute(
        "INSERT INTO clips(id, job_id, nvr_channel_id, requested_start_ms, requested_end_ms, "
        "status, created_ms, accessed_ms) VALUES "
        "('clip_1', 'job_1', 'channel_1', 100, 200, 'generating', 100, 100)"
    )

    database.initialize(200)

    row = database.one("SELECT status FROM clips WHERE id='clip_1'")
    assert row == {"status": "failed"}


def test_schema_v4_invalidates_pre_timezone_preview_cache(tmp_path: Path) -> None:
    database = Database(tmp_path / "preview-migration.sqlite")
    database.initialize(100)
    database.execute(
        "INSERT INTO sources(id, kind, external_source_id, last_seen_ms) "
        "VALUES ('source_1', 'nvr', 'fixture', 100)"
    )
    database.execute(
        "INSERT INTO source_channels(id, source_id, external_key, label, kind, created_ms, updated_ms) "
        "VALUES ('source_channel_1', 'source_1', '1', 'Camera', 'nvr_event', 100, 100)"
    )
    database.execute(
        "INSERT INTO intervals(id, source_id, source_event_id, source_channel_id, event_type, "
        "raw_start_ms, raw_end_ms, resolved_start_ms, resolved_end_ms, tags_json, attributes_json, "
        "created_ms, updated_ms) VALUES ('interval_1', 'source_1', 'event_1', 'source_channel_1', "
        "'nvr.motion', 100, 200, 100, 200, '[]', '{}', 100, 100)"
    )
    database.execute(
        "INSERT INTO event_previews(interval_id, status, relative_path, created_ms, updated_ms) "
        "VALUES ('interval_1', 'ready', 'previews/old.jpg', 100, 100)"
    )
    for table in (
        "trace_event_reviews",
        "trace_iteration_jobs",
        "trace_iterations",
        "trace_sessions",
    ):
        database.execute(f"DROP TABLE {table}")
    database.execute("DELETE FROM schema_migrations WHERE version IN (4, 5, 6)")

    database.initialize(200)

    assert database.one(
        "SELECT status, relative_path FROM event_previews WHERE interval_id='interval_1'"
    ) == {"status": "failed", "relative_path": None}
    assert database.one("SELECT MAX(version) AS version FROM schema_migrations") == {"version": 6}


def test_schema_v6_resets_only_untouched_context_padding_defaults(tmp_path: Path) -> None:
    database = Database(tmp_path / "settings-migration.sqlite")
    database.initialize(100)
    database.execute("DELETE FROM schema_migrations WHERE version=6")
    database.execute("UPDATE settings SET value_json='5000' WHERE key='pre_roll_ms'")
    database.execute("UPDATE settings SET value_json='2500' WHERE key='post_roll_ms'")

    database.initialize(200)

    settings = database.settings()
    assert settings["pre_roll_ms"] == 0
    assert settings["post_roll_ms"] == 2500


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
def test_dpapi_store_round_trips_without_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "secrets.dpapi.json"
    store = WindowsDpapiSecretStore(path)
    try:
        store.put("secret_fixture", "fixture-user", "never-store-plaintext")
    except FileNotFoundError:
        pytest.skip("DPAPI master-key profile is unavailable to the sandbox account")
    assert store.get("secret_fixture") == ("fixture-user", "never-store-plaintext")
    raw = path.read_text(encoding="utf-8")
    assert "fixture-user" not in raw
    assert "never-store-plaintext" not in raw
    assert isinstance(json.loads(raw)["secret_fixture"], str)
    store.delete("secret_fixture")
    assert "secret_fixture" not in path.read_text(encoding="utf-8")


def test_sqlite_never_receives_nvr_credentials(services, nvr) -> None:
    raw = services.config.database_path.read_bytes()
    assert b"secret-password" not in raw
    assert b"fixture-user" not in raw
