"""Durable fusion events. This module does not import mmwave-engine."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path


class FusionEventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS fusion_events(
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, event: dict[str, object]) -> None:
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "INSERT OR REPLACE INTO fusion_events VALUES (?, ?, ?, ?, ?)",
                (
                    str(event["event_id"]),
                    str(event["event_type"]),
                    str(event["zone_id"]),
                    float(event["timestamp"]),
                    json.dumps(event),
                ),
            )
            db.commit()

    def list_events(self) -> list[dict[str, object]]:
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT payload_json FROM fusion_events ORDER BY timestamp DESC"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
