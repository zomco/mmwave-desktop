"""SQLite migrations and small transactional data-access helpers."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


SCHEMA_VERSION = 2

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nvrs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    http_port INTEGER NOT NULL CHECK(http_port BETWEEN 1 AND 65535),
    use_https INTEGER NOT NULL CHECK(use_https IN (0, 1)),
    verify_tls INTEGER NOT NULL CHECK(verify_tls IN (0, 1)),
    model TEXT,
    firmware TEXT,
    timezone TEXT,
    clock_skew_ms INTEGER,
    secret_ref TEXT NOT NULL UNIQUE,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS nvr_capabilities (
    nvr_id TEXT NOT NULL REFERENCES nvrs(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('supported', 'unsupported', 'unknown', 'degraded')),
    evidence_json TEXT NOT NULL,
    observed_ms INTEGER NOT NULL,
    PRIMARY KEY (nvr_id, capability)
);
CREATE TABLE IF NOT EXISTS nvr_channels (
    id TEXT PRIMARY KEY,
    nvr_id TEXT NOT NULL REFERENCES nvrs(id) ON DELETE CASCADE,
    external_channel_id TEXT NOT NULL,
    primary_track_id TEXT,
    metadata_json TEXT NOT NULL,
    device_name TEXT NOT NULL,
    alias TEXT,
    online INTEGER NOT NULL CHECK(online IN (0, 1)),
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL,
    UNIQUE (nvr_id, external_channel_id)
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    external_source_id TEXT NOT NULL,
    version TEXT,
    last_seen_ms INTEGER NOT NULL,
    UNIQUE (kind, external_source_id)
);
CREATE TABLE IF NOT EXISTS source_channels (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_key TEXT NOT NULL,
    label TEXT NOT NULL,
    kind TEXT NOT NULL,
    nvr_channel_id TEXT REFERENCES nvr_channels(id) ON DELETE SET NULL,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL,
    UNIQUE (source_id, external_key)
);
CREATE TABLE IF NOT EXISTS spaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS space_media_channels (
    space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    nvr_channel_id TEXT NOT NULL REFERENCES nvr_channels(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('primary', 'secondary')),
    priority INTEGER NOT NULL DEFAULT 0,
    valid_from_ms INTEGER,
    valid_to_ms INTEGER,
    PRIMARY KEY (space_id, nvr_channel_id, valid_from_ms)
);
CREATE TABLE IF NOT EXISTS source_channel_bindings (
    source_channel_id TEXT NOT NULL REFERENCES source_channels(id) ON DELETE CASCADE,
    space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    clock_correction_ms INTEGER NOT NULL DEFAULT 0,
    valid_from_ms INTEGER,
    valid_to_ms INTEGER,
    PRIMARY KEY (source_channel_id, valid_from_ms)
);
CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    source_external_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('inspected', 'committed', 'rejected')),
    diagnostics_json TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    committed_ms INTEGER,
    UNIQUE (content_hash)
);
CREATE TABLE IF NOT EXISTS intervals (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_event_id TEXT NOT NULL,
    source_channel_id TEXT NOT NULL REFERENCES source_channels(id) ON DELETE CASCADE,
    nvr_channel_id TEXT REFERENCES nvr_channels(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    raw_start_ms INTEGER NOT NULL,
    raw_end_ms INTEGER NOT NULL CHECK(raw_end_ms > raw_start_ms),
    clock_correction_ms INTEGER NOT NULL DEFAULT 0,
    resolved_start_ms INTEGER NOT NULL,
    resolved_end_ms INTEGER NOT NULL CHECK(resolved_end_ms > resolved_start_ms),
    quality_gate TEXT CHECK(quality_gate IN ('pass', 'fail', 'unknown') OR quality_gate IS NULL),
    quality_score REAL CHECK(quality_score BETWEEN 0 AND 1 OR quality_score IS NULL),
    confidence REAL CHECK(confidence BETWEEN 0 AND 1 OR confidence IS NULL),
    media_start_ms INTEGER,
    media_end_ms INTEGER,
    tags_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    source_ref_json TEXT,
    import_id TEXT REFERENCES imports(id) ON DELETE SET NULL,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL,
    UNIQUE (source_id, source_event_id),
    CHECK(media_start_ms IS NULL OR media_end_ms > media_start_ms),
    CHECK(media_start_ms IS NULL OR media_start_ms <= resolved_start_ms),
    CHECK(media_end_ms IS NULL OR media_end_ms >= resolved_end_ms)
);
CREATE INDEX IF NOT EXISTS intervals_resolved_time ON intervals(resolved_start_ms, resolved_end_ms);
CREATE INDEX IF NOT EXISTS intervals_channel_time ON intervals(source_channel_id, resolved_start_ms);
CREATE TABLE IF NOT EXISTS recording_spans (
    id TEXT PRIMARY KEY,
    nvr_channel_id TEXT NOT NULL REFERENCES nvr_channels(id) ON DELETE CASCADE,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL CHECK(end_ms > start_ms),
    classification TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    observed_ms INTEGER NOT NULL,
    expires_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted')),
    progress REAL NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 1),
    error_code TEXT,
    error_message TEXT,
    error_details_json TEXT,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0, 1)),
    created_ms INTEGER NOT NULL,
    started_ms INTEGER,
    finished_ms INTEGER,
    updated_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_state_created ON jobs(state, created_ms);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    nvr_channel_id TEXT NOT NULL REFERENCES nvr_channels(id) ON DELETE CASCADE,
    requested_start_ms INTEGER NOT NULL,
    requested_end_ms INTEGER NOT NULL CHECK(requested_end_ms > requested_start_ms),
    actual_start_ms INTEGER,
    actual_end_ms INTEGER,
    relative_path TEXT,
    video_codec TEXT,
    audio_codec TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued', 'generating', 'ready', 'failed')),
    size_bytes INTEGER,
    created_ms INTEGER NOT NULL,
    accessed_ms INTEGER NOT NULL
);
"""

MIGRATION_2 = """
ALTER TABLE clips ADD COLUMN origin_json TEXT;
CREATE TABLE search_presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    nvr_id TEXT NOT NULL REFERENCES nvrs(id) ON DELETE CASCADE,
    area_name TEXT NOT NULL,
    channel_ids_json TEXT NOT NULL,
    event_types_json TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL,
    last_used_ms INTEGER
);
CREATE TABLE search_results (
    search_job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    interval_id TEXT NOT NULL REFERENCES intervals(id) ON DELETE CASCADE,
    PRIMARY KEY (search_job_id, interval_id)
);
CREATE TABLE nvr_event_audits (
    nvr_id TEXT PRIMARY KEY REFERENCES nvrs(id) ON DELETE CASCADE,
    report_json TEXT NOT NULL,
    observed_ms INTEGER NOT NULL
);
CREATE TABLE event_previews (
    interval_id TEXT PRIMARY KEY REFERENCES intervals(id) ON DELETE CASCADE,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK(status IN ('queued', 'generating', 'ready', 'failed')),
    relative_path TEXT,
    created_ms INTEGER NOT NULL,
    updated_ms INTEGER NOT NULL
);
"""


DEFAULT_SETTINGS = {
    "clip_quota_bytes": 10 * 1024 * 1024 * 1024,
    "pre_roll_ms": 5_000,
    "post_roll_ms": 10_000,
    "preferred_port": 8765,
}


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._write_lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self, now_ms: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock, closing(self.connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(MIGRATION_1)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_ms) VALUES (?, ?)",
                (1, now_ms),
            )
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current < 2:
                connection.executescript(MIGRATION_2)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_ms) VALUES (?, ?)",
                    (2, now_ms),
                )
            for key, value in DEFAULT_SETTINGS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO settings(key, value_json) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            connection.execute(
                """
                UPDATE jobs
                SET state='interrupted', error_code='JOB_INTERRUPTED',
                    error_message='Application stopped while the job was running.',
                    finished_ms=?, updated_ms=?
                WHERE state='running'
                """,
                (now_ms, now_ms),
            )
            connection.execute(
                """
                UPDATE clips
                SET status='failed'
                WHERE status IN ('queued', 'generating')
                  AND job_id IN (
                      SELECT id FROM jobs WHERE state IN ('failed', 'cancelled', 'interrupted')
                  )
                """
            )
            connection.execute(
                """
                UPDATE event_previews SET status='failed', updated_ms=?
                WHERE status IN ('queued', 'generating')
                  AND job_id IN (
                      SELECT id FROM jobs WHERE state IN ('failed', 'cancelled', 'interrupted')
                  )
                """,
                (now_ms,),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock, closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, parameters)
            return cursor.rowcount

    def one(self, sql: str, parameters: Sequence[Any] = ()) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(sql, parameters).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def settings(self) -> dict[str, Any]:
        return {row["key"]: json.loads(row["value_json"]) for row in self.all("SELECT key, value_json FROM settings")}

    def patch_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            for key, value in values.items():
                connection.execute(
                    "INSERT INTO settings(key, value_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                    (key, json.dumps(value)),
                )
        return self.settings()

    def schema_version(self) -> int:
        row = self.one("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
        return int(row["version"]) if row else 0
