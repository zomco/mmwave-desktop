"""Durable gateway interval store with bounded diagnostics."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from tracecue_engine import (
    Coverage,
    Interval,
    Producer,
    SourceChannel,
    TimelineDocument,
    dump_timeline,
    from_utc_millis,
    inspect_timeline,
    utc_millis,
)

from .clock import ClockSnapshot
from .models import Observation


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS gateway_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intervals(
    source_id TEXT NOT NULL,
    interval_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL CHECK(end_ms > start_ms),
    document_json TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    PRIMARY KEY(source_id, interval_id)
);
CREATE INDEX IF NOT EXISTS gateway_intervals_time ON intervals(start_ms, end_ms);
CREATE TABLE IF NOT EXISTS clock_observations(
    observed_ms INTEGER NOT NULL,
    estimated_skew_ms INTEGER,
    jitter_ms INTEGER,
    healthy INTEGER,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_diagnostics(
    observed_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
"""


class GatewayStore:
    def __init__(self, path: Path, *, diagnostic_limit: int = 1_000):
        self.path = path
        self.diagnostic_limit = diagnostic_limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.executescript(SCHEMA)

    def persist_observation(self, observation: Observation, clock: ClockSnapshot) -> None:
        observed_ms = utc_millis(observation.received_at)
        payload = {
            "source_id": observation.source_id,
            "channel_id": observation.channel_id,
            "track_id": observation.track_id,
            "source_at": observation.source_at.isoformat(),
            "x": observation.x,
            "y": observation.y,
        }
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "INSERT INTO clock_observations VALUES (?, ?, ?, ?, ?)",
                (
                    observed_ms,
                    clock.estimated_skew_ms,
                    clock.jitter_ms,
                    None if clock.healthy is None else int(clock.healthy),
                    clock.reason,
                ),
            )
            db.execute(
                "INSERT INTO raw_diagnostics VALUES (?, ?)",
                (observed_ms, json.dumps(payload)),
            )
            db.execute(
                """
                DELETE FROM raw_diagnostics WHERE rowid IN (
                    SELECT rowid FROM raw_diagnostics ORDER BY observed_ms DESC LIMIT -1 OFFSET ?
                )
                """,
                (self.diagnostic_limit,),
            )
            db.commit()

    def persist_interval(self, source_id: str, interval: Interval) -> None:
        single = TimelineDocument(
            "timeline.v1",
            f"gateway-single-{interval.id}",
            source_id,
            datetime.now(timezone.utc),
            Producer("tracecue-gateway", "0.1.0"),
            Coverage(interval.start_at, interval.end_at, "partial"),
            (SourceChannel(interval.channel_id, interval.channel_id, "mmwave"),),
            (interval,),
        )
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                """
                INSERT INTO intervals(source_id, interval_id, channel_id, start_ms, end_ms, document_json, created_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, interval_id) DO UPDATE SET document_json=excluded.document_json
                """,
                (
                    source_id,
                    interval.id,
                    interval.channel_id,
                    utc_millis(interval.start_at),
                    utc_millis(interval.end_at),
                    dump_timeline(single, pretty=False),
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                ),
            )
            db.commit()

    def export(
        self,
        *,
        source_id: str,
        channel: SourceChannel,
        start_at: datetime,
        end_at: datetime,
        complete: bool,
    ) -> TimelineDocument:
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """
                SELECT document_json FROM intervals
                WHERE source_id=? AND start_ms < ? AND end_ms > ? ORDER BY start_ms, interval_id
                """,
                (source_id, utc_millis(end_at), utc_millis(start_at)),
            ).fetchall()
        intervals = tuple(inspect_timeline(row[0]).document.intervals[0] for row in rows)
        return TimelineDocument(
            "timeline.v1",
            f"gateway-export-{utc_millis(start_at)}-{utc_millis(end_at)}",
            source_id,
            datetime.now(timezone.utc),
            Producer("tracecue-gateway", "0.1.0"),
            Coverage(start_at, end_at, "complete" if complete else "partial"),
            (channel,),
            intervals,
        )

    def interval_count(self) -> int:
        with closing(sqlite3.connect(self.path)) as db:
            return int(db.execute("SELECT COUNT(*) FROM intervals").fetchone()[0])

