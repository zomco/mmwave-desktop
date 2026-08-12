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
