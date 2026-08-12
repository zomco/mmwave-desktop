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
