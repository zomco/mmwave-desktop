"""Desktop application services and persistent background job execution."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlunsplit

from tracecue_engine import dump_timeline, from_utc_millis, inspect_timeline, utc_millis
from tracecue_hikvision import (
    ConnectionConfig,
    DigestTransport,
    HistoricalEventQuery,
    HikvisionAdapter,
    HikvisionError,
    RecordingQuery,
    discover_devices,
    playback_locator_for_device_time,
    playback_locator_for_window,
)

from .config import AppConfig
from .database import Database
from .errors import AppError, MediaError
from .media import FFmpegRunner
from .secrets import SecretStore, WindowsDpapiSecretStore
from .sharing import LanClipShareServer
from .vision import VisualAnalyzer, VisionError, build_visual_analyzer


CHANNEL_SNAPSHOT_TTL_MS = 10 * 60_000
ACTIVITY_CLUSTER_GAP_MS = 30_000
JOB_WORKER_COUNT = 2
TRACE_ACTIVITY_CTES = f"""
hits AS (
    SELECT DISTINCT sr.interval_id
    FROM trace_iterations ti
    JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
    JOIN search_results sr ON sr.search_job_id=tij.job_id
    WHERE ti.session_id=?
),
ordered_activity AS (
    SELECT i.id, i.resolved_start_ms, i.resolved_end_ms,
           MAX(i.resolved_end_ms) OVER (
               ORDER BY i.resolved_start_ms, i.id
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
           ) AS previous_max_end_ms
    FROM hits JOIN intervals i ON i.id=hits.interval_id
),
marked_activity AS (
    SELECT *, CASE
        WHEN previous_max_end_ms IS NULL
          OR resolved_start_ms > previous_max_end_ms + {ACTIVITY_CLUSTER_GAP_MS}
        THEN 1 ELSE 0 END AS cluster_start
    FROM ordered_activity
),
grouped_activity AS (
    SELECT *, SUM(cluster_start) OVER (
        ORDER BY resolved_start_ms, id ROWS UNBOUNDED PRECEDING
    ) AS cluster_id
    FROM marked_activity
),
activity_events AS (
    SELECT id, resolved_start_ms, resolved_end_ms, cluster_id,
           COUNT(*) OVER (PARTITION BY cluster_id) AS cluster_size
    FROM grouped_activity
)
"""


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def rfc3339(value_ms: int | None) -> str | None:
    if value_ms is None:
        return None
    rendered = from_utc_millis(value_ms).isoformat(timespec="milliseconds")
    return rendered.removesuffix("+00:00") + "Z"


def clamp_candidate_window(
    candidate_start_ms: int,
    candidate_end_ms: int,
    event_start_ms: int,
    event_end_ms: int,
    *,
    previous_event_end_ms: int | None = None,
    next_event_start_ms: int | None = None,
) -> tuple[int, int, bool]:
    """Trim only contextual padding at midpoints between adjacent event bodies."""
    def device_safe_midpoint(left_ms: int, right_ms: int) -> int:
        raw = left_ms + (right_ms - left_ms) // 2
        floor_second = raw - raw % 1_000
        if left_ms <= floor_second <= right_ms:
            return floor_second
        ceil_second = floor_second + 1_000
        if left_ms <= ceil_second <= right_ms:
            return ceil_second
        return raw

    start_ms = candidate_start_ms
    end_ms = candidate_end_ms
    if previous_event_end_ms is not None and previous_event_end_ms <= event_start_ms:
        midpoint = device_safe_midpoint(previous_event_end_ms, event_start_ms)
        start_ms = max(start_ms, min(event_start_ms, midpoint))
    if next_event_start_ms is not None and next_event_start_ms >= event_end_ms:
        midpoint = device_safe_midpoint(event_end_ms, next_event_start_ms)
        end_ms = min(end_ms, max(event_end_ms, midpoint))
    return start_ms, end_ms, start_ms != candidate_start_ms or end_ms != candidate_end_ms


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, datetime):
        rendered = value.astimezone(timezone.utc).isoformat(timespec="milliseconds")
        return rendered.removesuffix("+00:00") + "Z"
    if isinstance(value, Path):
        return str(value)
    return value


class DesktopServices:
    def __init__(
        self,
        config: AppConfig,
        *,
        secret_store: SecretStore | None = None,
        adapter_factory: Callable[[ConnectionConfig], HikvisionAdapter] | None = None,
        media_runner: FFmpegRunner | None = None,
        device_discoverer: Callable[[float], tuple[Any, ...]] | None = None,
        share_server: Any | None = None,
        visual_analyzer: VisualAnalyzer | None = None,
    ):
        self.config = config
        config.prepare()
        self.database = Database(config.database_path)
        self.database.initialize(now_ms())
        self.secret_store = secret_store or WindowsDpapiSecretStore(config.secret_path)
        self.adapter_factory = adapter_factory or (lambda connection: HikvisionAdapter(DigestTransport(connection)))
        self.media_runner = media_runner or FFmpegRunner(
            config.ffmpeg_path, config.ffprobe_path, config.clip_dir
        )
        self.device_discoverer = device_discoverer or discover_devices
        self.share_server = share_server or LanClipShareServer()
        self.visual_analyzer = visual_analyzer or build_visual_analyzer(config.vision_model_path)
        self.worker = JobWorker(self)

    def visual_analysis_availability(self) -> dict[str, Any]:
        return self.visual_analyzer.availability()

    def discover_nvrs(self, timeout_seconds: float) -> list[dict[str, Any]]:
        try:
            devices = self.device_discoverer(timeout_seconds)
        except (OSError, ValueError) as exc:
            raise AppError("NVR_DISCOVERY_FAILED", "Local device discovery could not complete.", 502) from exc
        configured = {
            (row["host"].lower(), int(row["http_port"]), bool(row["use_https"]))
            for row in self.database.all("SELECT host, http_port, use_https FROM nvrs")
        }
        result = []
        for device in devices:
            item = jsonable(device)
            item["already_added"] = (
                str(item["host"]).lower(), int(item["http_port"]), bool(item["use_https"])
            ) in configured
            result.append(item)
        return result

    def probe_nvr(self, values: dict[str, Any]) -> dict[str, Any]:
        connection = self._connection_from_values(values)
        try:
            report = self.adapter_factory(connection).probe()
        except HikvisionError as exc:
            raise AppError(exc.code, "The NVR probe failed.", 502) from exc
        result = jsonable(report)
        if result.get("device"):
            result["device"].pop("serial_number", None)
        return result

    def create_nvr(self, values: dict[str, Any]) -> dict[str, Any]:
        connection = self._connection_from_values(values)
        try:
            report = self.adapter_factory(connection).probe()
        except HikvisionError as exc:
            raise AppError(exc.code, "The NVR could not be added.", 502) from exc
        if not report.reachable:
            raise AppError("NVR_UNREACHABLE", "The NVR did not respond.", 502)
        if not report.authenticated:
            raise AppError("AUTH_INVALID", "The NVR rejected these credentials.", 401)
        if report.device is None:
            raise AppError("CAPABILITY_DEVICE_INFO_REQUIRED", "Device identity could not be read.", 422)
        timestamp = now_ms()
        nvr_id = new_id("nvr")
        secret_ref = new_id("secret")
        self.secret_store.put(secret_ref, connection.username, connection.password)
        try:
            with self.database.transaction() as db:
                db.execute(
                    """
                    INSERT INTO nvrs(
                        id, name, host, http_port, use_https, verify_tls, model, firmware,
                        timezone, clock_skew_ms, utc_offset_minutes, secret_ref, created_ms, updated_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nvr_id,
                        values.get("name") or report.device.model or connection.host,
                        connection.host,
                        connection.http_port,
                        int(connection.use_https),
                        int(connection.verify_tls),
                        report.device.model,
                        report.device.firmware,
                        report.clock.timezone if report.clock else None,
                        report.clock.estimated_skew_ms if report.clock else None,
                        report.clock.utc_offset_minutes if report.clock else None,
                        secret_ref,
                        timestamp,
                        timestamp,
                    ),
                )
                self._store_capabilities(db, nvr_id, report.capabilities)
        except BaseException:
            self.secret_store.delete(secret_ref)
            raise
        try:
            self.sync_channels(nvr_id)
            self.audit_nvr_events(nvr_id)
        except AppError:
            pass
        return self.get_nvr(nvr_id)

    def list_nvrs(self) -> list[dict[str, Any]]:
        return [self._public_nvr(row) for row in self.database.all("SELECT * FROM nvrs ORDER BY name, id")]

    def get_nvr(self, nvr_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM nvrs WHERE id=?", (nvr_id,))
        if not row:
            raise AppError("NVR_NOT_FOUND", "NVR was not found.", 404)
        return self._public_nvr(row)

    def nvr_details(self, nvr_id: str) -> dict[str, Any]:
        row = self._nvr_row(nvr_id)
        try:
            report = self._adapter_for_row(row).inspect_device_details()
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR device details could not be inspected.", 502) from exc
        payload = jsonable(report)
        payload["connection"] = {
            "host": row["host"],
            "http_port": int(row["http_port"]),
            "use_https": bool(row["use_https"]),
            "timezone": row["timezone"],
            "clock_skew_ms": row["clock_skew_ms"],
        }
        stored_channels = self.database.all(
            "SELECT id, external_channel_id, device_name, alias, online FROM nvr_channels WHERE nvr_id=?",
            (nvr_id,),
        )
        returned = {item["external_channel_id"]: item for item in payload["cameras"]}
        for channel in stored_channels:
            details = returned.get(channel["external_channel_id"])
            if details is None:
                details = {
                    "external_channel_id": channel["external_channel_id"],
                    "name": channel["device_name"],
                    "online": bool(channel["online"]),
                    "model": None,
                    "firmware": None,
                    "serial_number": None,
                    "device_id": None,
                    "protocol": None,
                    "address": None,
                    "manage_port": None,
                    "source_input_port": None,
                    "stream_type": None,
                }
                payload["cameras"].append(details)
            details["channel_id"] = channel["id"]
            details["label"] = channel["alias"] or channel["device_name"]
        payload["cameras"].sort(key=lambda item: item["external_channel_id"])
        return payload

    def patch_nvr(self, nvr_id: str, values: dict[str, Any]) -> dict[str, Any]:
        current = self._nvr_row(nvr_id)
        allowed = {"name", "host", "http_port", "use_https", "verify_tls"}
        changes = {key: value for key, value in values.items() if key in allowed and value is not None}
        username = values.get("username")
        password = values.get("password")
        if (username is None) != (password is None):
            raise AppError("AUTH_CREDENTIALS_INCOMPLETE", "Username and password must be updated together.", 422)
        if changes:
            assignments = ", ".join(f"{key}=?" for key in changes)
            self.database.execute(
                f"UPDATE nvrs SET {assignments}, updated_ms=? WHERE id=?",
                (*changes.values(), now_ms(), nvr_id),
            )
        if username is not None:
            self.secret_store.put(current["secret_ref"], username, password)
        return self.get_nvr(nvr_id)

    def delete_nvr(self, nvr_id: str) -> None:
        row = self._nvr_row(nvr_id)
        channel_ids = {
            item["id"] for item in self.database.all(
                "SELECT id FROM nvr_channels WHERE nvr_id=?", (nvr_id,)
            )
        }
        affected_sessions = [
            item["id"] for item in self.database.all(
                "SELECT id, channel_ids_json FROM trace_sessions"
            )
            if channel_ids.intersection(json.loads(item["channel_ids_json"]))
        ]
        clip_rows = self.database.all(
            """
            SELECT c.relative_path FROM clips c
            JOIN nvr_channels nc ON nc.id=c.nvr_channel_id
            WHERE nc.nvr_id=? AND c.relative_path IS NOT NULL
            """,
            (nvr_id,),
        )
        preview_rows = self.database.all(
            """
            SELECT p.relative_path FROM event_previews p
            JOIN intervals i ON i.id=p.interval_id
            JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
            WHERE nc.nvr_id=? AND p.relative_path IS NOT NULL
            """,
            (nvr_id,),
        )
        animation_rows = self.database.all(
            """
            SELECT a.relative_path FROM event_animations a
            JOIN intervals i ON i.id=a.interval_id
            JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
            WHERE nc.nvr_id=? AND a.relative_path IS NOT NULL
            """,
            (nvr_id,),
        )
        snapshot_rows = self.database.all(
            """
            SELECT s.relative_path FROM channel_snapshots s
            JOIN nvr_channels nc ON nc.id=s.channel_id
            WHERE nc.nvr_id=? AND s.relative_path IS NOT NULL
            """,
            (nvr_id,),
        )
        with self.database.transaction() as db:
            for session_id in affected_sessions:
                db.execute("DELETE FROM trace_sessions WHERE id=?", (session_id,))
            db.execute(
                "DELETE FROM sources WHERE kind='nvr' AND external_source_id=?",
                (nvr_id,),
            )
            db.execute("DELETE FROM nvrs WHERE id=?", (nvr_id,))
        self.secret_store.delete(row["secret_ref"])
        for artifact in [*clip_rows, *preview_rows, *animation_rows, *snapshot_rows]:
            path = (self.config.clip_dir / artifact["relative_path"]).resolve()
            if path.is_relative_to(self.config.clip_dir.resolve()):
                path.unlink(missing_ok=True)

    def sync_channels(self, nvr_id: str) -> list[dict[str, Any]]:
        nvr = self._nvr_row(nvr_id)
        adapter = self._adapter_for_row(nvr)
        try:
            channels = adapter.list_channels()
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR channels could not be synchronized.", 502) from exc
        timestamp = now_ms()
        seen: set[str] = set()
        with self.database.transaction() as db:
            for channel in channels:
                channel_id = stable_id("channel", nvr_id, channel.external_id)
                seen.add(channel.external_id)
                db.execute(
                    """
                    INSERT INTO nvr_channels(
                        id, nvr_id, external_channel_id, primary_track_id, metadata_json,
                        device_name, alias, online, created_ms, updated_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                    ON CONFLICT(nvr_id, external_channel_id) DO UPDATE SET
                        primary_track_id=excluded.primary_track_id,
                        metadata_json=excluded.metadata_json,
                        device_name=excluded.device_name,
                        online=excluded.online,
                        updated_ms=excluded.updated_ms
                    """,
                    (
                        channel_id,
                        nvr_id,
                        channel.external_id,
                        channel.stream_track_ids[0] if channel.stream_track_ids else None,
                        json.dumps({"stream_track_ids": list(channel.stream_track_ids), "input_port": channel.input_port}),
                        channel.name,
                        int(channel.enabled),
                        timestamp,
                        timestamp,
                    ),
                )
            if seen:
                placeholders = ",".join("?" for _ in seen)
                db.execute(
                    f"UPDATE nvr_channels SET online=0, updated_ms=? WHERE nvr_id=? AND external_channel_id NOT IN ({placeholders})",
                    (timestamp, nvr_id, *sorted(seen)),
                )
        return self.list_channels(nvr_id)

    def list_channels(self, nvr_id: str) -> list[dict[str, Any]]:
        self._nvr_row(nvr_id)
        rows = self.database.all("SELECT * FROM nvr_channels WHERE nvr_id=? ORDER BY external_channel_id", (nvr_id,))
        return [self._public_channel(row) for row in rows]

    def capabilities(self, nvr_id: str) -> list[dict[str, Any]]:
        self._nvr_row(nvr_id)
        rows = self.database.all(
            "SELECT capability, status, evidence_json, observed_ms FROM nvr_capabilities WHERE nvr_id=? ORDER BY capability",
            (nvr_id,),
        )
        for row in rows:
            row["evidence"] = json.loads(row.pop("evidence_json"))
            row["observed_at"] = rfc3339(row.pop("observed_ms"))
        return rows

    def audit_nvr_events(self, nvr_id: str) -> dict[str, Any]:
        nvr = self._nvr_row(nvr_id)
        adapter = self._adapter_for_row(nvr)
        try:
            report = adapter.inspect_event_settings(adapter.list_channels())
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR event settings could not be inspected.", 502) from exc
        payload = jsonable(report)
        payload["schema_version"] = 4
        labels = {
            row["external_channel_id"]: row["alias"] or row["device_name"]
            for row in self.database.all(
                "SELECT external_channel_id, alias, device_name FROM nvr_channels WHERE nvr_id=?",
                (nvr_id,),
            )
        }
        for rule in payload["rules"]:
            rule["channel_label"] = labels.get(
                rule["channel_external_id"], f"Channel {rule['channel_external_id']}"
            )
        observed_ms = self._external_time(payload["observed_at"], "observed_at")
        self.database.execute(
            """
            INSERT INTO nvr_event_audits(nvr_id, report_json, observed_ms) VALUES (?, ?, ?)
            ON CONFLICT(nvr_id) DO UPDATE SET report_json=excluded.report_json,
                observed_ms=excluded.observed_ms
            """,
            (nvr_id, json.dumps(payload), observed_ms),
        )
        return payload

    def get_event_audit(self, nvr_id: str) -> dict[str, Any]:
        self._nvr_row(nvr_id)
        row = self.database.one(
            "SELECT report_json FROM nvr_event_audits WHERE nvr_id=?", (nvr_id,)
        )
        if not row:
            raise AppError("EVENT_AUDIT_NOT_RUN", "Event settings have not been inspected yet.", 404)
        payload = json.loads(row["report_json"])
        if payload.get("schema_version") != 4:
            return self.audit_nvr_events(nvr_id)
        return payload

    def patch_channel(self, channel_id: str, values: dict[str, Any]) -> dict[str, Any]:
        if "alias" not in values:
            raise AppError("CHANNEL_PATCH_EMPTY", "No supported channel field was provided.", 422)
        updated = self.database.execute(
            "UPDATE nvr_channels SET alias=?, updated_ms=? WHERE id=?",
            (values.get("alias"), now_ms(), channel_id),
        )
        if not updated:
            raise AppError("NVR_CHANNEL_NOT_FOUND", "NVR channel was not found.", 404)
        return self._public_channel(self._channel_row(channel_id))

    def enqueue_channel_snapshot(self, channel_id: str) -> dict[str, Any]:
        self._channel_row(channel_id)
        timestamp = now_ms()
        existing = self.database.one("SELECT * FROM channel_snapshots WHERE channel_id=?", (channel_id,))
        usable_cache = bool(
            existing
            and existing["relative_path"]
            and self._derived_path_exists(existing["relative_path"])
        )
        active_refresh = bool(
            existing
            and existing["job_id"]
            and (
                job := self.database.one(
                    "SELECT state FROM jobs WHERE id=?", (existing["job_id"],)
                )
            )
            and job["state"] in {"queued", "running"}
        )
        if active_refresh:
            return self._public_channel_snapshot(existing)
        if (
            existing and usable_cache
            and int(existing["expires_ms"] or 0) > timestamp
        ):
            return self._public_channel_snapshot(existing)
        job_id = new_id("job")
        payload = {"channel_id": channel_id}
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms) "
                "VALUES (?, 'channel_snapshot', 'queued', ?, 0, ?, ?)",
                (job_id, json.dumps(payload), timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO channel_snapshots(
                    channel_id, job_id, status, relative_path, captured_ms, expires_ms,
                    created_ms, updated_ms
                ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET job_id=excluded.job_id,
                    status=excluded.status,
                    updated_ms=excluded.updated_ms
                """,
                (channel_id, job_id, "ready" if usable_cache else "queued", timestamp, timestamp),
            )
        return self.get_channel_snapshot(channel_id)

    def get_channel_snapshot(self, channel_id: str) -> dict[str, Any]:
        self._channel_row(channel_id)
        row = self.database.one("SELECT * FROM channel_snapshots WHERE channel_id=?", (channel_id,))
        if not row:
            raise AppError("MEDIA_SNAPSHOT_NOT_FOUND", "Camera snapshot has not been requested.", 404)
        return self._public_channel_snapshot(row)

    def channel_snapshot_file(self, channel_id: str) -> Path:
        row = self.database.one("SELECT * FROM channel_snapshots WHERE channel_id=?", (channel_id,))
        if not row or not row["relative_path"]:
            raise AppError("MEDIA_SNAPSHOT_NOT_READY", "Camera snapshot is not ready.", 409)
        path = (self.config.clip_dir / row["relative_path"]).resolve()
        if not path.is_relative_to(self.config.clip_dir.resolve()) or not path.is_file():
            raise AppError("STORAGE_SNAPSHOT_MISSING", "Camera snapshot file is missing.", 410)
        return path

    def enqueue_search(self, values: dict[str, Any]) -> dict[str, Any]:
        nvr_id = values["nvr_id"]
        self._nvr_row(nvr_id)
        channel_ids = values.get("channel_ids") or []
        if len(channel_ids) != 1:
            raise AppError("NVR_CHANNEL_REQUIRED", "Select exactly one NVR camera.", 422)
        start_ms = self._external_time(values["from"], "from")
        end_ms = self._external_time(values["to"], "to")
        if end_ms <= start_ms:
            raise AppError("TIMELINE_RANGE_INVALID", "Search end must be after start.", 422)
        for channel_id in channel_ids:
            channel = self._channel_row(channel_id)
            if channel["nvr_id"] != nvr_id:
                raise AppError("NVR_CHANNEL_MISMATCH", "A channel does not belong to the selected NVR.", 422)
        event_types = [str(value).strip().lower() for value in values.get("event_types") or [] if str(value).strip()]
        if len(event_types) != 1:
            raise AppError("EVENT_FILTER_REQUIRED", "Select exactly one event type.", 422)
        if any(len(value) > 100 for value in event_types):
            raise AppError("EVENT_FILTER_INVALID", "An event type filter is too long.", 422)
        preset_id = values.get("preset_id")
        if preset_id:
            preset = self.database.one("SELECT nvr_id, scope_json, channel_ids_json FROM search_presets WHERE id=?", (preset_id,))
            preset_channels = json.loads((preset or {}).get("scope_json") or (preset or {}).get("channel_ids_json") or "[]")
            preset_nvrs = {
                self._channel_row(channel_id)["nvr_id"] for channel_id in preset_channels
            } if preset else set()
            if not preset or nvr_id not in preset_nvrs:
                raise AppError("SEARCH_PRESET_NOT_FOUND", "The saved search filter was not found for this NVR.", 404)
            self.database.execute(
                "UPDATE search_presets SET last_used_ms=?, updated_ms=? WHERE id=?",
                (now_ms(), now_ms(), preset_id),
            )
        return self._enqueue_job(
            "recording_search",
            {
                "nvr_id": nvr_id,
                "channel_ids": channel_ids,
                "from_ms": start_ms,
                "to_ms": end_ms,
                "source_modes": values.get("source_modes") or ["record_classification"],
                "area_name": values.get("area_name") or "",
                "event_types": list(dict.fromkeys(event_types)),
                "preset_id": preset_id,
            },
        )

    def list_search_presets(self) -> list[dict[str, Any]]:
        rows = self.database.all(
            "SELECT * FROM search_presets ORDER BY COALESCE(last_used_ms, updated_ms) DESC"
        )
        return [self._public_search_preset(row) for row in rows]

    def create_search_preset(self, values: dict[str, Any]) -> dict[str, Any]:
        channel_ids = list(dict.fromkeys(values["channel_ids"]))
        if len(channel_ids) != 1:
            raise AppError("NVR_CHANNEL_REQUIRED", "Select exactly one camera.", 422)
        event_types = list(dict.fromkeys(values.get("event_types") or []))
        if len(event_types) != 1:
            raise AppError("EVENT_FILTER_REQUIRED", "Select exactly one event type.", 422)
        nvr_ids: list[str] = []
        for channel_id in channel_ids:
            channel = self._channel_row(channel_id)
            if channel["nvr_id"] not in nvr_ids:
                nvr_ids.append(channel["nvr_id"])
        primary_nvr_id = values.get("nvr_id") or nvr_ids[0]
        if primary_nvr_id not in nvr_ids:
            raise AppError("NVR_CHANNEL_MISMATCH", "The preset recorder does not match its cameras.", 422)
        preset_id = new_id("preset")
        timestamp = now_ms()
        self.database.execute(
            """
            INSERT INTO search_presets(
                id, name, nvr_id, area_name, channel_ids_json, event_types_json,
                created_ms, updated_ms, last_used_ms, scope_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                preset_id, values["name"].strip(), primary_nvr_id,
                (values.get("area_name") or "").strip(), json.dumps(channel_ids),
                json.dumps(event_types),
                timestamp, timestamp, timestamp, json.dumps(channel_ids),
            ),
        )
        row = self.database.one("SELECT * FROM search_presets WHERE id=?", (preset_id,))
        return self._public_search_preset(row)

    def delete_search_preset(self, preset_id: str) -> None:
        if not self.database.execute("DELETE FROM search_presets WHERE id=?", (preset_id,)):
            raise AppError("SEARCH_PRESET_NOT_FOUND", "The saved search filter was not found.", 404)

    def list_trace_sessions(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.database.all(
            "SELECT * FROM trace_sessions ORDER BY updated_ms DESC, id DESC LIMIT ?", (limit,)
        )
        return [self._public_trace_session(row) for row in rows]

    def create_trace_session(self, values: dict[str, Any]) -> dict[str, Any]:
        channel_ids = list(dict.fromkeys(values.get("channel_ids") or []))
        if len(channel_ids) != 1:
            raise AppError("NVR_CHANNEL_REQUIRED", "Select exactly one camera.", 422)
        for channel_id in channel_ids:
            self._channel_row(channel_id)
        event_types = [
            str(value).strip().lower()
            for value in values.get("event_types") or []
            if str(value).strip()
        ]
        event_types = list(dict.fromkeys(event_types))
        if len(event_types) != 1:
            raise AppError("EVENT_FILTER_REQUIRED", "Select exactly one event type.", 422)
        if any(len(value) > 100 for value in event_types):
            raise AppError("EVENT_FILTER_INVALID", "An event type filter is too long.", 422)
        preset_id = values.get("preset_id")
        if preset_id and not self.database.one(
            "SELECT id FROM search_presets WHERE id=?", (preset_id,)
        ):
            raise AppError("SEARCH_PRESET_NOT_FOUND", "The saved search filter was not found.", 404)
        session_id = new_id("trace")
        timestamp = now_ms()
        self.database.execute(
            """
            INSERT INTO trace_sessions(
                id, channel_ids_json, event_types_json, preset_id, created_ms, updated_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                json.dumps(channel_ids),
                json.dumps(event_types),
                preset_id,
                timestamp,
                timestamp,
            ),
        )
        return self.get_trace_session(session_id)

    def get_trace_session(self, session_id: str) -> dict[str, Any]:
        return self._public_trace_session(self._trace_session_row(session_id))

    def delete_trace_session(self, session_id: str) -> None:
        self._trace_session_row(session_id)
        self.database.execute("DELETE FROM trace_sessions WHERE id=?", (session_id,))

    def create_trace_iteration(
        self, session_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        session = self._trace_session_row(session_id)
        start_ms = self._external_time(values["from"], "from")
        end_ms = self._external_time(values["to"], "to")
        if end_ms <= start_ms:
            raise AppError("TIMELINE_RANGE_INVALID", "Search end must be after start.", 422)
        existing = self.database.one(
            "SELECT id FROM trace_iterations WHERE session_id=? AND from_ms=? AND to_ms=?",
            (session_id, start_ms, end_ms),
        )
        if existing:
            return self.get_trace_session(session_id)
        if self.database.one(
            "SELECT id FROM trace_iterations WHERE session_id=? LIMIT 1", (session_id,)
        ):
            raise AppError(
                "TRACE_SESSION_WINDOW_FIXED",
                "This Trace search already has a time window. Start a new search to change it.",
                409,
            )

        channel_ids = json.loads(session["channel_ids_json"])
        grouped: dict[str, list[str]] = {}
        for channel_id in channel_ids:
            channel = self._channel_row(channel_id)
            grouped.setdefault(channel["nvr_id"], []).append(channel_id)
        iteration_id = new_id("iteration")
        timestamp = now_ms()
        self.database.execute(
            """
            INSERT INTO trace_iterations(
                id, session_id, from_ms, to_ms, label, created_ms, updated_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iteration_id,
                session_id,
                start_ms,
                end_ms,
                str(values.get("label") or "自定义时间").strip(),
                timestamp,
                timestamp,
            ),
        )
        try:
            for nvr_id, grouped_channels in grouped.items():
                job = self.enqueue_search(
                    {
                        "nvr_id": nvr_id,
                        "channel_ids": grouped_channels,
                        "from": values["from"],
                        "to": values["to"],
                        "source_modes": ["record_classification"],
                        "event_types": json.loads(session["event_types_json"]),
                        "preset_id": session["preset_id"],
                    }
                )
                self.database.execute(
                    "INSERT INTO trace_iteration_jobs(iteration_id, job_id) VALUES (?, ?)",
                    (iteration_id, job["id"]),
                )
        except BaseException:
            self.database.execute("DELETE FROM trace_iterations WHERE id=?", (iteration_id,))
            raise
        self.database.execute(
            "UPDATE trace_sessions SET updated_ms=? WHERE id=?", (timestamp, session_id)
        )
        return self.get_trace_session(session_id)

    def trace_session_results(
        self,
        session_id: str,
        *,
        limit: int = 12,
        offset: int = 0,
        review_state: str = "active",
        from_at: str | None = None,
        to_at: str | None = None,
        duration_class: str | None = None,
        min_duration_ms: int | None = None,
        max_duration_ms: int | None = None,
        activity_mode: str = "all",
        summary_only: bool = False,
    ) -> dict[str, Any]:
        self._trace_session_row(session_id)
        if not 1 <= limit <= 200 or not 0 <= offset <= 100_000:
            raise AppError("SEARCH_PAGE_INVALID", "Search page bounds are invalid.", 422)
        allowed_states = {"active", "all", "unreviewed", "reviewed", "excluded", "candidate"}
        if review_state not in allowed_states:
            raise AppError("TRACE_REVIEW_FILTER_INVALID", "Review-state filter is invalid.", 422)
        duration_classes = {"unknown", "under_5s", "5_to_30s", "over_30s"}
        if duration_class is not None and duration_class not in duration_classes:
            raise AppError("TRACE_DURATION_FILTER_INVALID", "Event-duration filter is invalid.", 422)
        if activity_mode not in {"all", "isolated", "clustered"}:
            raise AppError("TRACE_ACTIVITY_FILTER_INVALID", "Event-activity filter is invalid.", 422)
        if min_duration_ms is not None and not 0 <= min_duration_ms <= 86_400_000:
            raise AppError("TRACE_DURATION_FILTER_INVALID", "Minimum event duration is invalid.", 422)
        if max_duration_ms is not None and not 0 <= max_duration_ms <= 86_400_000:
            raise AppError("TRACE_DURATION_FILTER_INVALID", "Maximum event duration is invalid.", 422)
        if (
            min_duration_ms is not None
            and max_duration_ms is not None
            and max_duration_ms < min_duration_ms
        ):
            raise AppError(
                "TRACE_DURATION_FILTER_INVALID",
                "Maximum event duration must not be shorter than the minimum.",
                422,
            )

        review_filters: list[str] = []
        review_parameters: list[Any] = []
        if review_state == "active":
            review_filters.append("COALESCE(r.state, 'unreviewed') != 'excluded'")
        elif review_state != "all":
            review_filters.append("COALESCE(r.state, 'unreviewed') = ?")
            review_parameters.append(review_state)

        time_filters: list[str] = []
        time_parameters: list[Any] = []
        selected_window: dict[str, str] | None = None
        if (from_at is None) != (to_at is None):
            raise AppError("TRACE_TIME_FILTER_INVALID", "Both time-filter bounds are required.", 422)
        if from_at is not None and to_at is not None:
            filter_start = self._external_time(from_at, "from")
            filter_end = self._external_time(to_at, "to")
            if filter_end <= filter_start:
                raise AppError("TIMELINE_RANGE_INVALID", "Result filter end must be after start.", 422)
            # An event belongs to a selected window when their intervals overlap.
            # Start-only filtering drops events that begin before a dragged range.
            time_filters.append("i.resolved_start_ms < ? AND i.resolved_end_ms > ?")
            time_parameters.extend((filter_end, filter_start))
            selected_window = {"start_at": rfc3339(filter_start), "end_at": rfc3339(filter_end)}

        duration_expression = (
            "CAST(json_extract(i.attributes_json, '$.hikvision.event_duration_ms') AS INTEGER)"
        )
        duration_filters: list[str] = []
        duration_parameters: list[Any] = []
        if duration_class == "unknown":
            duration_filters.append(f"{duration_expression} IS NULL")
        elif duration_class == "under_5s":
            duration_filters.append(f"{duration_expression} >= 0 AND {duration_expression} < 5000")
        elif duration_class == "5_to_30s":
            duration_filters.append(f"{duration_expression} >= 5000 AND {duration_expression} <= 30000")
        elif duration_class == "over_30s":
            duration_filters.append(f"{duration_expression} > 30000")
        if min_duration_ms is not None:
            duration_filters.append(f"{duration_expression} >= ?")
            duration_parameters.append(min_duration_ms)
        if max_duration_ms is not None:
            duration_filters.append(f"{duration_expression} <= ?")
            duration_parameters.append(max_duration_ms)

        activity_filters: list[str] = []
        if activity_mode == "isolated":
            activity_filters.append("ae.cluster_size = 1")
        elif activity_mode == "clustered":
            activity_filters.append("ae.cluster_size > 1")

        result_filters = [*review_filters, *time_filters, *activity_filters, *duration_filters]
        result_parameters = [*review_parameters, *time_parameters, *duration_parameters]
        result_filter_clause = " AND " + " AND ".join(result_filters) if result_filters else ""
        time_filter_clause = " AND " + " AND ".join(time_filters) if time_filters else ""
        activity_filter_clause = (
            " AND " + " AND ".join(activity_filters) if activity_filters else ""
        )

        rows: list[dict[str, Any]] = []
        if not summary_only:
            rows = self.database.all(
                f"""
                WITH ranked_hits AS (
                    SELECT sr.interval_id, tij.job_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY sr.interval_id ORDER BY j.created_ms DESC, j.id DESC
                           ) AS hit_rank
                    FROM trace_iterations ti
                    JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
                    JOIN jobs j ON j.id=tij.job_id
                    JOIN search_results sr ON sr.search_job_id=tij.job_id
                    WHERE ti.session_id=?
                ), latest_hits AS (
                    SELECT interval_id, job_id FROM ranked_hits WHERE hit_rank=1
                ), {TRACE_ACTIVITY_CTES}
                SELECT i.*, sc.label AS source_channel_label, sc.kind AS source_channel_kind,
                       s.kind AS source_kind, s.external_source_id,
                       COALESCE(nc.alias, nc.device_name) AS media_channel_label,
                       latest_hits.job_id AS trace_search_job_id,
                       COALESCE(r.state, 'unreviewed') AS trace_review_state
                FROM latest_hits
                JOIN intervals i ON i.id=latest_hits.interval_id
                JOIN activity_events ae ON ae.id=i.id
                JOIN source_channels sc ON sc.id=i.source_channel_id
                JOIN sources s ON s.id=i.source_id
                LEFT JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
                LEFT JOIN trace_event_reviews r
                  ON r.session_id=? AND r.interval_id=i.id
                WHERE 1=1 {result_filter_clause}
                ORDER BY i.resolved_start_ms DESC, i.id DESC
                LIMIT ? OFFSET ?
                """,
                (
                    session_id,
                    session_id,
                    session_id,
                    *result_parameters,
                    limit,
                    offset,
                ),
            )

        counts = {state: 0 for state in ("unreviewed", "reviewed", "excluded", "candidate")}
        for row in self.database.all(
            """
            WITH hits AS (
                SELECT DISTINCT sr.interval_id
                FROM trace_iterations ti
                JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
                JOIN search_results sr ON sr.search_job_id=tij.job_id
                WHERE ti.session_id=?
            )
            SELECT COALESCE(r.state, 'unreviewed') AS state, COUNT(*) AS count
            FROM hits
            LEFT JOIN trace_event_reviews r
              ON r.session_id=? AND r.interval_id=hits.interval_id
            GROUP BY COALESCE(r.state, 'unreviewed')
            """,
            (session_id, session_id),
        ):
            counts[row["state"]] = int(row["count"])

        timeline_rows = self.database.all(
            f"""
            WITH {TRACE_ACTIVITY_CTES}
            SELECT i.id, i.resolved_start_ms, i.resolved_end_ms,
                   CAST(json_extract(i.attributes_json, '$.hikvision.event_duration_ms') AS INTEGER) AS duration_ms,
                   ae.cluster_size
            FROM hits
            JOIN intervals i ON i.id=hits.interval_id
            JOIN activity_events ae ON ae.id=i.id
            ORDER BY i.resolved_start_ms, i.id
            LIMIT 2001
            """,
            (session_id,),
        )
        timeline_truncated = len(timeline_rows) > 2_000
        timeline = [
            {
                "id": row["id"],
                "start_at": rfc3339(int(row["resolved_start_ms"])),
                "end_at": rfc3339(int(row["resolved_end_ms"])),
                "duration_ms": int(row["duration_ms"]) if row["duration_ms"] is not None else None,
                "cluster_size": int(row["cluster_size"]),
            }
            for row in timeline_rows[:2_000]
        ]

        duration_buckets = {key: 0 for key in ("unknown", "under_5s", "5_to_30s", "over_30s")}
        for row in self.database.all(
            f"""
            WITH {TRACE_ACTIVITY_CTES}
            SELECT {duration_expression} AS duration_ms
            FROM hits
            JOIN intervals i ON i.id=hits.interval_id
            JOIN activity_events ae ON ae.id=i.id
            WHERE 1=1 {time_filter_clause} {activity_filter_clause}
            """,
            (session_id, *time_parameters),
        ):
            duration_ms = row["duration_ms"]
            if duration_ms is None:
                duration_buckets["unknown"] += 1
            elif int(duration_ms) < 5_000:
                duration_buckets["under_5s"] += 1
            elif int(duration_ms) <= 30_000:
                duration_buckets["5_to_30s"] += 1
            else:
                duration_buckets["over_30s"] += 1

        activity_counts = {"isolated": 0, "clustered": 0}
        for row in self.database.all(
            f"""
            WITH {TRACE_ACTIVITY_CTES}
            SELECT CASE WHEN ae.cluster_size > 1 THEN 'clustered' ELSE 'isolated' END AS mode,
                   COUNT(*) AS count
            FROM hits
            JOIN intervals i ON i.id=hits.interval_id
            JOIN activity_events ae ON ae.id=i.id
            WHERE 1=1 {time_filter_clause}
            GROUP BY CASE WHEN ae.cluster_size > 1 THEN 'clustered' ELSE 'isolated' END
            """,
            (session_id, *time_parameters),
        ):
            activity_counts[row["mode"]] = int(row["count"])

        duration_range_row = self.database.one(
            f"""
            WITH {TRACE_ACTIVITY_CTES}
            SELECT COUNT({duration_expression}) AS known_count,
                   MIN({duration_expression}) AS min_ms,
                   MAX({duration_expression}) AS max_ms
            FROM hits
            JOIN intervals i ON i.id=hits.interval_id
            JOIN activity_events ae ON ae.id=i.id
            WHERE 1=1 {time_filter_clause} {activity_filter_clause}
            """,
            (session_id, *time_parameters),
        ) or {"known_count": 0, "min_ms": None, "max_ms": None}
        duration_range = {
            "known_count": int(duration_range_row["known_count"] or 0),
            "min_ms": (
                int(duration_range_row["min_ms"])
                if duration_range_row["min_ms"] is not None else None
            ),
            "max_ms": (
                int(duration_range_row["max_ms"])
                if duration_range_row["max_ms"] is not None else None
            ),
        }
        items: list[dict[str, Any]] = []
        for row in rows:
            item = self._public_interval(row)
            item["review_state"] = row["trace_review_state"]
            item["search_job_id"] = row["trace_search_job_id"]
            items.append(item)
        filtered = self.database.one(
            f"""
            WITH {TRACE_ACTIVITY_CTES}
            SELECT COUNT(*) AS total
            FROM hits
            JOIN intervals i ON i.id=hits.interval_id
            JOIN activity_events ae ON ae.id=i.id
            LEFT JOIN trace_event_reviews r
              ON r.session_id=? AND r.interval_id=i.id
            WHERE 1=1 {result_filter_clause}
            """,
            (session_id, session_id, *result_parameters),
        )
        filtered_total = int(filtered["total"] if filtered else 0)
        return {
            "session_id": session_id,
            "items": items,
            "total": filtered_total,
            "counts": counts,
            "timeline": timeline,
            "timeline_truncated": timeline_truncated,
            "selected_window": selected_window,
            "duration_buckets": duration_buckets,
            "duration_range": duration_range,
            "activity_mode": activity_mode,
            "activity_counts": activity_counts,
            "activity_cluster_gap_ms": ACTIVITY_CLUSTER_GAP_MS,
            "limit": limit,
            "offset": offset,
            "has_more": not summary_only and offset + len(items) < filtered_total,
            "summary_only": summary_only,
        }

    def patch_trace_review(
        self, session_id: str, bookmark_id: str, state: str
    ) -> dict[str, Any]:
        self._trace_session_row(session_id)
        belongs = self.database.one(
            """
            SELECT 1 AS found
            FROM trace_iterations ti
            JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
            JOIN search_results sr ON sr.search_job_id=tij.job_id
            WHERE ti.session_id=? AND sr.interval_id=? LIMIT 1
            """,
            (session_id, bookmark_id),
        )
        if not belongs:
            raise AppError(
                "TRACE_RESULT_MISMATCH", "The event does not belong to this Trace session.", 422
            )
        timestamp = now_ms()
        if state == "unreviewed":
            self.database.execute(
                "DELETE FROM trace_event_reviews WHERE session_id=? AND interval_id=?",
                (session_id, bookmark_id),
            )
        else:
            self.database.execute(
                """
                INSERT INTO trace_event_reviews(session_id, interval_id, state, updated_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, interval_id) DO UPDATE SET
                    state=excluded.state, updated_ms=excluded.updated_ms
                """,
                (session_id, bookmark_id, state, timestamp),
            )
        self.database.execute(
            "UPDATE trace_sessions SET updated_ms=? WHERE id=?", (timestamp, session_id)
        )
        return {
            "session_id": session_id,
            "bookmark_id": bookmark_id,
            "state": state,
            "updated_at": rfc3339(timestamp),
        }

    def search_results(self, job_id: str, *, limit: int = 12, offset: int = 0) -> dict[str, Any]:
        job = self.database.one("SELECT kind, state, result_json FROM jobs WHERE id=?", (job_id,))
        if not job or job["kind"] != "recording_search":
            raise AppError("JOB_NOT_FOUND", "Search job was not found.", 404)
        if not 1 <= limit <= 200 or not 0 <= offset <= 100_000:
            raise AppError("SEARCH_PAGE_INVALID", "Search page bounds are invalid.", 422)
        count = self.database.one(
            "SELECT COUNT(*) AS total FROM search_results WHERE search_job_id=?", (job_id,)
        )
        rows = self.database.all(
            """
            SELECT i.*, sc.label AS source_channel_label, sc.kind AS source_channel_kind,
                   s.kind AS source_kind, s.external_source_id,
                   COALESCE(nc.alias, nc.device_name) AS media_channel_label
            FROM search_results sr
            JOIN intervals i ON i.id=sr.interval_id
            JOIN source_channels sc ON sc.id=i.source_channel_id
            JOIN sources s ON s.id=i.source_id
            LEFT JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
            WHERE sr.search_job_id=?
            ORDER BY i.resolved_start_ms DESC, i.id DESC
            LIMIT ? OFFSET ?
            """,
            (job_id, limit, offset),
        )
        total = int(count["total"] if count else 0)
        return {
            "job_id": job_id,
            "state": job["state"],
            "items": [self._public_interval(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }

    def list_bookmarks(self, *, limit: int, cursor: str | None, high_confidence: bool | None) -> dict[str, Any]:
        if not 1 <= limit <= 200:
            raise AppError("TIMELINE_LIMIT_INVALID", "Bookmark limit must be between 1 and 200.", 422)
        parameters: list[Any] = []
        where: list[str] = []
        if cursor:
            try:
                cursor_ms, cursor_id = cursor.split(":", 1)
                parameters.extend((int(cursor_ms), int(cursor_ms), cursor_id))
            except (ValueError, TypeError) as exc:
                raise AppError("TIMELINE_CURSOR_INVALID", "Bookmark cursor is invalid.", 400) from exc
            where.append("(i.resolved_start_ms < ? OR (i.resolved_start_ms = ? AND i.id < ?))")
        if high_confidence is True:
            where.append("i.quality_gate='pass'")
        elif high_confidence is False:
            where.append("COALESCE(i.quality_gate, 'unknown')!='pass'")
        clause = " WHERE " + " AND ".join(where) if where else ""
        rows = self.database.all(
            """
            SELECT i.*, sc.label AS source_channel_label, sc.kind AS source_channel_kind,
                   s.kind AS source_kind, s.external_source_id,
                   COALESCE(nc.alias, nc.device_name) AS media_channel_label
            FROM intervals i
            JOIN source_channels sc ON sc.id=i.source_channel_id
            JOIN sources s ON s.id=i.source_id
            LEFT JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
            """ + clause + " ORDER BY i.resolved_start_ms DESC, i.id DESC LIMIT ?",
            (*parameters, limit + 1),
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._public_interval(row) for row in rows]
        next_cursor = f"{rows[-1]['resolved_start_ms']}:{rows[-1]['id']}" if has_more and rows else None
        return {"items": items, "next_cursor": next_cursor}

    def get_bookmark(self, bookmark_id: str) -> dict[str, Any]:
        row = self.database.one(
            """
            SELECT i.*, sc.label AS source_channel_label, sc.kind AS source_channel_kind,
                   s.kind AS source_kind, s.external_source_id,
                   COALESCE(nc.alias, nc.device_name) AS media_channel_label
            FROM intervals i
            JOIN source_channels sc ON sc.id=i.source_channel_id
            JOIN sources s ON s.id=i.source_id
            LEFT JOIN nvr_channels nc ON nc.id=i.nvr_channel_id
            WHERE i.id=?
            """,
            (bookmark_id,),
        )
        if not row:
            raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Bookmark was not found.", 404)
        return self._public_interval(row)

    def enqueue_event_preview(self, bookmark_id: str) -> dict[str, Any]:
        interval = self.database.one("SELECT * FROM intervals WHERE id=?", (bookmark_id,))
        if not interval:
            raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Event was not found.", 404)
        existing = self.database.one("SELECT * FROM event_previews WHERE interval_id=?", (bookmark_id,))
        if existing and existing["status"] in {"queued", "generating", "ready"}:
            if existing["status"] != "ready" or self._derived_path_exists(existing["relative_path"]):
                return self._public_event_preview(existing)
        channel_id = interval["nvr_channel_id"] or self._mapped_media_channel(interval)
        self._channel_row(channel_id)
        job_id = new_id("job")
        timestamp = now_ms()
        payload = {
            "interval_id": bookmark_id,
            "channel_id": channel_id,
            "start_ms": max(0, interval["resolved_start_ms"] - 3_000),
            "end_ms": interval["resolved_start_ms"] + 12_000,
        }
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms) "
                "VALUES (?, 'event_preview', 'queued', ?, 0, ?, ?)",
                (job_id, json.dumps(payload), timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO event_previews(interval_id, job_id, status, relative_path, created_ms, updated_ms)
                VALUES (?, ?, 'queued', NULL, ?, ?)
                ON CONFLICT(interval_id) DO UPDATE SET job_id=excluded.job_id,
                    status='queued', relative_path=NULL, updated_ms=excluded.updated_ms
                """,
                (bookmark_id, job_id, timestamp, timestamp),
            )
        return self.get_event_preview(bookmark_id)

    def get_event_preview(self, bookmark_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM event_previews WHERE interval_id=?", (bookmark_id,))
        if not row:
            raise AppError("MEDIA_PREVIEW_NOT_FOUND", "Event preview has not been requested.", 404)
        return self._public_event_preview(row)

    def event_preview_file(self, bookmark_id: str) -> Path:
        row = self.database.one("SELECT * FROM event_previews WHERE interval_id=?", (bookmark_id,))
        if not row or row["status"] != "ready" or not row["relative_path"]:
            raise AppError("MEDIA_PREVIEW_NOT_READY", "Event preview is not ready.", 409)
        path = (self.config.clip_dir / row["relative_path"]).resolve()
        if not path.is_relative_to(self.config.clip_dir.resolve()) or not path.is_file():
            raise AppError("STORAGE_PREVIEW_MISSING", "Event preview file is missing.", 410)
        return path

    def enqueue_event_animation(self, bookmark_id: str) -> dict[str, Any]:
        interval = self.database.one("SELECT * FROM intervals WHERE id=?", (bookmark_id,))
        if not interval:
            raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Event was not found.", 404)
        existing = self.database.one("SELECT * FROM event_animations WHERE interval_id=?", (bookmark_id,))
        if existing and existing["status"] in {"queued", "generating", "ready"}:
            if existing["status"] != "ready" or self._derived_path_exists(existing["relative_path"]):
                return self._public_event_animation(existing)
        channel_id = interval["nvr_channel_id"] or self._mapped_media_channel(interval)
        self._channel_row(channel_id)
        job_id = new_id("job")
        timestamp = now_ms()
        payload = {
            "interval_id": bookmark_id,
            "channel_id": channel_id,
            "start_ms": max(0, interval["resolved_start_ms"] - 1_000),
            "end_ms": interval["resolved_start_ms"] + 4_000,
        }
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms) "
                "VALUES (?, 'event_animation', 'queued', ?, 0, ?, ?)",
                (job_id, json.dumps(payload), timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO event_animations(interval_id, job_id, status, relative_path, created_ms, updated_ms)
                VALUES (?, ?, 'queued', NULL, ?, ?)
                ON CONFLICT(interval_id) DO UPDATE SET job_id=excluded.job_id,
                    status='queued', relative_path=NULL, updated_ms=excluded.updated_ms
                """,
                (bookmark_id, job_id, timestamp, timestamp),
            )
        return self.get_event_animation(bookmark_id)

    def get_event_animation(self, bookmark_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM event_animations WHERE interval_id=?", (bookmark_id,))
        if not row:
            raise AppError("MEDIA_ANIMATION_NOT_FOUND", "Event hover preview has not been requested.", 404)
        return self._public_event_animation(row)

    def event_animation_file(self, bookmark_id: str) -> Path:
        row = self.database.one("SELECT * FROM event_animations WHERE interval_id=?", (bookmark_id,))
        if not row or row["status"] != "ready" or not row["relative_path"]:
            raise AppError("MEDIA_ANIMATION_NOT_READY", "Event hover preview is not ready.", 409)
        path = (self.config.clip_dir / row["relative_path"]).resolve()
        if not path.is_relative_to(self.config.clip_dir.resolve()) or not path.is_file():
            raise AppError("STORAGE_ANIMATION_MISSING", "Event hover preview file is missing.", 410)
        return path

    def enqueue_event_visual_analysis(self, bookmark_id: str) -> dict[str, Any]:
        interval = self.database.one("SELECT * FROM intervals WHERE id=?", (bookmark_id,))
        if not interval:
            raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Event was not found.", 404)
        attributes = json.loads(interval["attributes_json"])
        event_type = str(
            attributes.get("hikvision", {}).get("canonical_event_type")
            or interval["event_type"].removeprefix("nvr.")
        )
        if event_type not in {"line_crossing", "region_intrusion"}:
            raise AppError(
                "VISION_EVENT_TYPE_UNSUPPORTED",
                "Visual validation currently supports line crossing and region intrusion.",
                422,
            )
        available = self.visual_analysis_availability()
        if not available.get("available"):
            raise AppError(
                str(available.get("code") or "VISION_ANALYZER_UNAVAILABLE"),
                str(available.get("message") or "Visual analysis is unavailable."),
                409,
                {"visual_analysis": available},
            )
        channel_id = interval["nvr_channel_id"] or self._mapped_media_channel(interval)
        channel = self._channel_row(channel_id)
        analysis_start_ms = max(0, int(interval["resolved_start_ms"]) - 5_000)
        desired_end_ms = max(
            int(interval["resolved_end_ms"]) + 5_000,
            int(interval["resolved_start_ms"]) + 10_000,
        )
        analysis_end_ms = min(analysis_start_ms + 30_000, desired_end_ms)
        overlays = self._visual_rule_overlays(channel, event_type)
        analysis_signature = hashlib.sha256(
            json.dumps(
                {
                    "event_type": event_type,
                    "model_id": available.get("model_id"),
                    "overlays": overlays,
                    "sample": {"width": 416, "height": 416, "fps": 5},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        existing = self.database.one(
            "SELECT * FROM event_visual_analyses WHERE interval_id=?", (bookmark_id,)
        )
        if existing and existing["status"] in {"queued", "analyzing"}:
            return self._public_event_visual_analysis(existing)
        if existing and existing["status"] == "ready":
            cached = json.loads(existing["result_json"] or "{}")
            if cached.get("analysis_signature") == analysis_signature:
                return self._public_event_visual_analysis(existing)
        job_id = new_id("job")
        timestamp = now_ms()
        payload = {
            "interval_id": bookmark_id,
            "channel_id": channel_id,
            "event_type": event_type,
            "start_ms": analysis_start_ms,
            "end_ms": analysis_end_ms,
            "overlays": overlays,
            "analysis_signature": analysis_signature,
        }
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms) "
                "VALUES (?, 'event_visual_analysis', 'queued', ?, 0, ?, ?)",
                (job_id, json.dumps(payload), timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO event_visual_analyses(
                    interval_id, job_id, status, verdict, result_json, created_ms, updated_ms
                ) VALUES (?, ?, 'queued', NULL, NULL, ?, ?)
                ON CONFLICT(interval_id) DO UPDATE SET job_id=excluded.job_id,
                    status='queued', verdict=NULL, result_json=NULL, updated_ms=excluded.updated_ms
                """,
                (bookmark_id, job_id, timestamp, timestamp),
            )
        return self.get_event_visual_analysis(bookmark_id)

    def get_event_visual_analysis(self, bookmark_id: str) -> dict[str, Any]:
        if not self.database.one("SELECT id FROM intervals WHERE id=?", (bookmark_id,)):
            raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Event was not found.", 404)
        row = self.database.one(
            "SELECT * FROM event_visual_analyses WHERE interval_id=?", (bookmark_id,)
        )
        if not row:
            raise AppError(
                "VISION_ANALYSIS_NOT_REQUESTED", "Visual analysis has not been requested.", 404
            )
        return self._public_event_visual_analysis(row)

    def _visual_rule_overlays(
        self, channel: dict[str, Any], event_type: str
    ) -> list[dict[str, Any]]:
        audit = self.database.one(
            "SELECT report_json FROM nvr_event_audits WHERE nvr_id=?", (channel["nvr_id"],)
        )
        if not audit:
            return []
        report = json.loads(audit["report_json"])
        rules = [
            rule for rule in report.get("rules", [])
            if str(rule.get("channel_external_id")) == str(channel["external_channel_id"])
            and rule.get("event_type") == event_type
            and rule.get("enabled") is not False
        ]
        return [overlay for rule in rules for overlay in rule.get("overlays", [])][:8]

    def _derived_path_exists(self, relative_path: str | None) -> bool:
        if not relative_path:
            return False
        path = (self.config.clip_dir / relative_path).resolve()
        return path.is_relative_to(self.config.clip_dir.resolve()) and path.is_file()

    def _set_job_progress(self, job_id: str, progress: float) -> None:
        self.database.execute(
            "UPDATE jobs SET progress=?, updated_ms=? WHERE id=?",
            (max(0.0, min(1.0, progress)), now_ms(), job_id),
        )

    def _job_progress(self, job_id: str) -> float:
        row = self.database.one("SELECT progress FROM jobs WHERE id=?", (job_id,))
        return float(row["progress"]) if row else 0.0

    def enqueue_clip(self, values: dict[str, Any]) -> dict[str, Any]:
        settings = self.database.settings()
        bookmark_id = values.get("bookmark_id")
        if bookmark_id:
            interval = self.database.one("SELECT * FROM intervals WHERE id=?", (bookmark_id,))
            if not interval:
                raise AppError("TIMELINE_INTERVAL_NOT_FOUND", "Bookmark was not found.", 404)
            channel_id = interval["nvr_channel_id"] or self._mapped_media_channel(interval)
            override = values.get("window_override") or {}
            pre = int(override.get("pre_roll_ms", settings["pre_roll_ms"]))
            post = int(override.get("post_roll_ms", settings["post_roll_ms"]))
            search_job_id = values.get("search_job_id")
            if search_job_id:
                link = self.database.one(
                    "SELECT 1 AS found FROM search_results WHERE search_job_id=? AND interval_id=?",
                    (search_job_id, bookmark_id),
                )
                if not link:
                    raise AppError("SEARCH_RESULT_MISMATCH", "The event does not belong to that search session.", 422)
            else:
                latest = self.database.one(
                    """
                    SELECT sr.search_job_id FROM search_results sr
                    JOIN jobs j ON j.id=sr.search_job_id
                    WHERE sr.interval_id=? ORDER BY j.created_ms DESC LIMIT 1
                    """,
                    (bookmark_id,),
                )
                search_job_id = latest["search_job_id"] if latest else None

            start_ms = interval["media_start_ms"] if interval["media_start_ms"] is not None else interval["resolved_start_ms"] - pre
            end_ms = interval["media_end_ms"] if interval["media_end_ms"] is not None else interval["resolved_end_ms"] + post
            previous_event_end_ms: int | None = None
            next_event_start_ms: int | None = None
            if search_job_id and channel_id:
                previous = self.database.one(
                    """
                    SELECT neighbor.resolved_end_ms
                    FROM search_results sr
                    JOIN intervals neighbor ON neighbor.id=sr.interval_id
                    WHERE sr.search_job_id=? AND neighbor.id!=? AND neighbor.nvr_channel_id=?
                      AND neighbor.resolved_end_ms<=?
                    ORDER BY neighbor.resolved_end_ms DESC, neighbor.id DESC LIMIT 1
                    """,
                    (search_job_id, bookmark_id, channel_id, interval["resolved_start_ms"]),
                )
                following = self.database.one(
                    """
                    SELECT neighbor.resolved_start_ms
                    FROM search_results sr
                    JOIN intervals neighbor ON neighbor.id=sr.interval_id
                    WHERE sr.search_job_id=? AND neighbor.id!=? AND neighbor.nvr_channel_id=?
                      AND neighbor.resolved_start_ms>=?
                    ORDER BY neighbor.resolved_start_ms, neighbor.id LIMIT 1
                    """,
                    (search_job_id, bookmark_id, channel_id, interval["resolved_end_ms"]),
                )
                previous_event_end_ms = int(previous["resolved_end_ms"]) if previous else None
                next_event_start_ms = int(following["resolved_start_ms"]) if following else None
            start_ms, end_ms, padding_trimmed = clamp_candidate_window(
                int(start_ms),
                int(end_ms),
                int(interval["resolved_start_ms"]),
                int(interval["resolved_end_ms"]),
                previous_event_end_ms=previous_event_end_ms,
                next_event_start_ms=next_event_start_ms,
            )
            uncapped_end_ms = end_ms
            max_duration_ms = override.get("max_duration_ms")
            if max_duration_ms is not None and end_ms - start_ms > int(max_duration_ms):
                end_ms = start_ms + int(max_duration_ms)
            bookmark = self.get_bookmark(bookmark_id)
            attributes = bookmark.get("attributes", {}).get("hikvision", {})
            origin = {
                "bookmark_id": bookmark_id,
                "search_job_id": search_job_id,
                "area_name": attributes.get("area_name"),
                "channel_label": bookmark["media_channel_label"],
                "event_type": bookmark["event_type"],
                "classification": attributes.get("classification"),
                "event_window": {"start_at": bookmark["start_at"], "end_at": bookmark["end_at"]},
                "padding_trimmed_for_neighbor_events": padding_trimmed,
                "candidate_window_capped": end_ms < uncapped_end_ms,
                "time_basis": "nvr_index",
            }
        else:
            channel_id = values.get("channel_id")
            if not channel_id or not values.get("from") or not values.get("to"):
                raise AppError("MEDIA_REQUEST_INVALID", "Provide a bookmark or an explicit channel and time window.", 422)
            start_ms = self._external_time(values["from"], "from")
            end_ms = self._external_time(values["to"], "to")
            origin = None
        if start_ms < 0 or end_ms <= start_ms:
            raise AppError("TIMELINE_RANGE_INVALID", "Clip end must be after start.", 422)
        self._channel_row(channel_id)
        timestamp = now_ms()
        clip_id = new_id("clip")
        job_id = new_id("job")
        payload = {
            "clip_id": clip_id,
            "channel_id": channel_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "audio_policy": values.get("audio_policy", "prefer"),
        }
        with self.database.transaction() as db:
            db.execute(
                """
                INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms)
                VALUES (?, 'clip', 'queued', ?, 0, ?, ?)
                """,
                (job_id, json.dumps(payload), timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO clips(id, job_id, nvr_channel_id, requested_start_ms, requested_end_ms,
                                  status, created_ms, accessed_ms, origin_json)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (clip_id, job_id, channel_id, start_ms, end_ms, timestamp, timestamp, json.dumps(origin) if origin else None),
            )
        return self.get_clip(clip_id)

    def list_clips(self) -> list[dict[str, Any]]:
        return [self._public_clip(row) for row in self.database.all("SELECT * FROM clips ORDER BY created_ms DESC")]

    def get_clip(self, clip_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row:
            raise AppError("MEDIA_CLIP_NOT_FOUND", "Clip was not found.", 404)
        return self._public_clip(row)

    def create_clip_share(self, clip_id: str) -> dict[str, Any]:
        path, _size = self.clip_file(clip_id)
        row = self.database.one(
            """
            SELECT c.*, n.host, COALESCE(ch.alias, ch.device_name) AS channel_label
            FROM clips c
            JOIN nvr_channels ch ON ch.id=c.nvr_channel_id
            JOIN nvrs n ON n.id=ch.nvr_id
            WHERE c.id=?
            """,
            (clip_id,),
        )
        if not row:
            raise AppError("MEDIA_CLIP_NOT_FOUND", "Clip was not found.", 404)
        try:
            share = self.share_server.create_share(
                clip_id=clip_id,
                path=path,
                title=row["channel_label"] or "TraceCue video clip",
                route_target=row["host"],
            )
        except OSError as exc:
            raise AppError(
                "LAN_SHARE_UNAVAILABLE",
                "A private LAN address is not available for temporary clip sharing.",
                409,
            ) from exc
        return {
            "clip_id": clip_id,
            "url": share["url"],
            "expires_at": rfc3339(int(share["expires_at_ms"])),
        }

    def stop_network_shares(self) -> None:
        self.share_server.stop()

    def clip_file(self, clip_id: str) -> tuple[Path, int]:
        row = self.database.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row or row["status"] != "ready" or not row["relative_path"]:
            raise AppError("MEDIA_CLIP_NOT_READY", "Clip is not ready for playback.", 409)
        path = (self.config.clip_dir / row["relative_path"]).resolve()
        if path.parent != self.config.clip_dir.resolve() or not path.is_file():
            raise AppError("STORAGE_CLIP_MISSING", "Clip file is missing.", 410)
        self.database.execute("UPDATE clips SET accessed_ms=? WHERE id=?", (now_ms(), clip_id))
        return path, path.stat().st_size

    def delete_clip(self, clip_id: str) -> None:
        row = self.database.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row:
            raise AppError("MEDIA_CLIP_NOT_FOUND", "Clip was not found.", 404)
        path = None
        if row["relative_path"]:
            candidate = (self.config.clip_dir / row["relative_path"]).resolve()
            if candidate.parent != self.config.clip_dir.resolve():
                raise AppError("STORAGE_PATH_INVALID", "Clip path is outside the configured directory.", 500)
            path = candidate
        self.database.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        if path:
            path.unlink(missing_ok=True)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [self._public_job(row) for row in self.database.all("SELECT * FROM jobs ORDER BY created_ms DESC")]

    def get_job(self, job_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise AppError("JOB_NOT_FOUND", "Job was not found.", 404)
        return self._public_job(row)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT state FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise AppError("JOB_NOT_FOUND", "Job was not found.", 404)
        if row["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            raise AppError("JOB_NOT_CANCELLABLE", "Job is already in a terminal state.", 409)
        timestamp = now_ms()
        self.database.execute(
            """
            UPDATE jobs SET cancel_requested=1,
                state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
                finished_ms=CASE WHEN state='queued' THEN ? ELSE finished_ms END,
                updated_ms=? WHERE id=?
            """,
            (timestamp, timestamp, job_id),
        )
        return self.get_job(job_id)

    def inspect_import(self, content: bytes) -> dict[str, Any]:
        try:
            inspection = inspect_timeline(content)
        except Exception as exc:
            issues = getattr(exc, "issues", ())
            raise AppError(
                "TIMELINE_INVALID",
                "Timeline document did not pass validation.",
                422,
                {"issues": [jsonable(item) for item in issues]},
            ) from exc
        existing = self.database.one("SELECT id FROM imports WHERE content_hash=?", (inspection.content_hash,))
        if existing:
            return self.get_import(existing["id"])
        document = inspection.document
        mapping_status = []
        source = self.database.one(
            "SELECT id FROM sources WHERE kind='timeline' AND external_source_id=?",
            (document.source_id,),
        )
        for channel in document.channels:
            mapped = False
            if source:
                row = self.database.one(
                    """
                    SELECT 1 FROM source_channels sc
                    JOIN source_channel_bindings b ON b.source_channel_id=sc.id
                    WHERE sc.source_id=? AND sc.external_key=? LIMIT 1
                    """,
                    (source["id"], channel.id),
                )
                mapped = row is not None
            mapping_status.append({"channel_id": channel.id, "label": channel.label, "mapped": mapped})
        import_id = new_id("import")
        timestamp = now_ms()
        diagnostics = {"valid": True, "channels": mapping_status, "interval_count": len(document.intervals)}
        self.database.execute(
            """
            INSERT INTO imports(id, document_id, source_external_id, content_hash, content_json,
                                status, diagnostics_json, created_ms)
            VALUES (?, ?, ?, ?, ?, 'inspected', ?, ?)
            """,
            (
                import_id,
                document.document_id,
                document.source_id,
                inspection.content_hash,
                dump_timeline(document, pretty=False),
                json.dumps(diagnostics),
                timestamp,
            ),
        )
        return self.get_import(import_id)

    def get_import(self, import_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not row:
            raise AppError("TIMELINE_IMPORT_NOT_FOUND", "Timeline import was not found.", 404)
        source_summary = self.database.all(
            "SELECT kind, COUNT(*) AS count, MAX(last_seen_ms) AS last_seen_ms FROM sources GROUP BY kind"
        )
        for source in source_summary:
            source["last_seen_at"] = rfc3339(source.pop("last_seen_ms"))
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "source_id": row["source_external_id"],
            "content_hash": row["content_hash"],
            "status": row["status"],
            "diagnostics": json.loads(row["diagnostics_json"]),
            "created_at": rfc3339(row["created_ms"]),
            "committed_at": rfc3339(row["committed_ms"]),
        }

    def commit_import(self, import_id: str, content_hash: str | None = None) -> dict[str, Any]:
        imported = self.database.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not imported:
            raise AppError("TIMELINE_IMPORT_NOT_FOUND", "Timeline import was not found.", 404)
        if content_hash and content_hash != imported["content_hash"]:
            raise AppError("TIMELINE_HASH_MISMATCH", "Inspected content hash does not match.", 409)
        if imported["status"] == "committed":
            return self.get_import(import_id)
        inspection = inspect_timeline(imported["content_json"])
        document = inspection.document
        timestamp = now_ms()
        source_id = stable_id("source", "timeline", document.source_id)
        with self.database.transaction() as db:
            db.execute(
                """
                INSERT INTO sources(id, kind, external_source_id, version, last_seen_ms)
                VALUES (?, 'timeline', ?, ?, ?)
                ON CONFLICT(kind, external_source_id) DO UPDATE SET version=excluded.version, last_seen_ms=excluded.last_seen_ms
                """,
                (source_id, document.source_id, document.producer.version, timestamp),
            )
            for channel in document.channels:
                source_channel_id = stable_id("source_channel", source_id, channel.id)
                db.execute(
                    """
                    INSERT INTO source_channels(id, source_id, external_key, label, kind, created_ms, updated_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, external_key) DO UPDATE SET
                        label=excluded.label, kind=excluded.kind, updated_ms=excluded.updated_ms
                    """,
                    (source_channel_id, source_id, channel.id, channel.label, channel.kind, timestamp, timestamp),
                )
            for interval in document.intervals:
                source_channel_id = stable_id("source_channel", source_id, interval.channel_id)
                binding = db.execute(
                    "SELECT clock_correction_ms FROM source_channel_bindings WHERE source_channel_id=? AND valid_to_ms IS NULL ORDER BY valid_from_ms DESC LIMIT 1",
                    (source_channel_id,),
                ).fetchone()
                correction = int(binding[0]) if binding else 0
                raw_start = utc_millis(interval.start_at)
                raw_end = utc_millis(interval.end_at)
                media_start = utc_millis(interval.media_window.start_at) + correction if interval.media_window else None
                media_end = utc_millis(interval.media_window.end_at) + correction if interval.media_window else None
                interval_id = stable_id("interval", source_id, interval.id)
                quality_gate = interval.quality.gate if interval.quality else None
                quality_score = interval.quality.score if interval.quality else None
                db.execute(
                    """
                    INSERT INTO intervals(
                        id, source_id, source_event_id, source_channel_id, event_type,
                        raw_start_ms, raw_end_ms, clock_correction_ms, resolved_start_ms, resolved_end_ms,
                        quality_gate, quality_score, confidence, media_start_ms, media_end_ms,
                        tags_json, attributes_json, source_ref_json, import_id, created_ms, updated_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, source_event_id) DO UPDATE SET
                        source_channel_id=excluded.source_channel_id, event_type=excluded.event_type,
                        raw_start_ms=excluded.raw_start_ms, raw_end_ms=excluded.raw_end_ms,
                        clock_correction_ms=excluded.clock_correction_ms,
                        resolved_start_ms=excluded.resolved_start_ms, resolved_end_ms=excluded.resolved_end_ms,
                        quality_gate=excluded.quality_gate, quality_score=excluded.quality_score,
                        confidence=excluded.confidence, media_start_ms=excluded.media_start_ms,
                        media_end_ms=excluded.media_end_ms, tags_json=excluded.tags_json,
                        attributes_json=excluded.attributes_json, source_ref_json=excluded.source_ref_json,
                        import_id=excluded.import_id, updated_ms=excluded.updated_ms
                    """,
                    (
                        interval_id,
                        source_id,
                        interval.id,
                        source_channel_id,
                        interval.event_type,
                        raw_start,
                        raw_end,
                        correction,
                        raw_start + correction,
                        raw_end + correction,
                        quality_gate,
                        quality_score,
                        interval.confidence,
                        media_start,
                        media_end,
                        json.dumps(interval.tags),
                        json.dumps(interval.attributes),
                        json.dumps(jsonable(interval.source_ref)) if interval.source_ref else None,
                        import_id,
                        timestamp,
                        timestamp,
                    ),
                )
            db.execute(
                "UPDATE imports SET status='committed', committed_ms=? WHERE id=?",
                (timestamp, import_id),
            )
        return self.get_import(import_id)

    def list_sources(self) -> list[dict[str, Any]]:
        rows = self.database.all("SELECT * FROM sources ORDER BY kind, external_source_id")
        for row in rows:
            row["last_seen_at"] = rfc3339(row.pop("last_seen_ms"))
        return rows

    def diagnostics(self) -> dict[str, Any]:
        """Return a support bundle preview with an explicit redaction inventory."""
        nvrs = self.database.all(
            "SELECT id, name, model, firmware, timezone, clock_skew_ms, updated_ms FROM nvrs ORDER BY name"
        )
        for nvr in nvrs:
            nvr["updated_at"] = rfc3339(nvr.pop("updated_ms"))
            nvr["address"] = "redacted"
        capabilities = self.database.all(
            "SELECT nvr_id, capability, status, evidence_json, observed_ms FROM nvr_capabilities ORDER BY nvr_id, capability"
        )
        for capability in capabilities:
            evidence = json.loads(capability.pop("evidence_json"))
            capability["evidence"] = {
                "endpoint": evidence.get("endpoint"),
                "status_code": evidence.get("status_code"),
                "fixture_hash": evidence.get("fixture_hash"),
                "note": evidence.get("note"),
            }
            capability["observed_at"] = rfc3339(capability.pop("observed_ms"))
        return {
            "bundle_version": 1,
            "generated_at": rfc3339(now_ms()),
            "schema_version": self.database.schema_version(),
            "settings": self.database.settings(),
            "nvrs": nvrs,
            "capabilities": capabilities,
            "channel_summary": self.database.all(
                "SELECT nvr_id, COUNT(*) AS total, SUM(online) AS online FROM nvr_channels GROUP BY nvr_id"
            ),
            "job_summary": self.database.all(
                "SELECT kind, state, COUNT(*) AS count FROM jobs GROUP BY kind, state ORDER BY kind, state"
            ),
            "clip_summary": self.database.all(
                "SELECT status, COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS size_bytes FROM clips GROUP BY status"
            ),
            "source_summary": self.database.all(
                "SELECT kind, COUNT(*) AS count, MAX(last_seen_ms) AS last_seen_ms FROM sources GROUP BY kind"
            ),
            "redaction": {
                "removed": [
                    "NVR host addresses",
                    "usernames and passwords",
                    "secret references",
                    "authorization headers",
                    "RTSP playback locators",
                    "filesystem paths",
                    "raw upstream bodies",
                ],
                "review_before_sharing": True,
            },
        }

    def list_source_channels(self) -> list[dict[str, Any]]:
        rows = self.database.all(
            """
            SELECT sc.*, s.external_source_id, s.kind AS source_kind,
                   b.space_id, b.clock_correction_ms, sp.name AS space_name,
                   smc.nvr_channel_id
            FROM source_channels sc
            JOIN sources s ON s.id=sc.source_id
            LEFT JOIN source_channel_bindings b ON b.source_channel_id=sc.id AND b.valid_to_ms IS NULL
            LEFT JOIN spaces sp ON sp.id=b.space_id
            LEFT JOIN space_media_channels smc ON smc.space_id=sp.id AND smc.role='primary' AND smc.valid_to_ms IS NULL
            ORDER BY s.external_source_id, sc.label
            """
        )
        for row in rows:
            row.pop("created_ms", None)
            row.pop("updated_ms", None)
        return rows

    def bind_source_channel(self, source_channel_id: str, values: dict[str, Any]) -> dict[str, Any]:
        source_channel = self.database.one("SELECT * FROM source_channels WHERE id=?", (source_channel_id,))
        if not source_channel:
            raise AppError("MAPPING_SOURCE_CHANNEL_NOT_FOUND", "Source channel was not found.", 404)
        media_channel_id = values.get("nvr_channel_id")
        self._channel_row(media_channel_id)
        space_id = values.get("space_id")
        space_name = values.get("space_name")
        timestamp = now_ms()
        correction = int(values.get("clock_correction_ms", 0))
        with self.database.transaction() as db:
            if space_id:
                space = db.execute("SELECT id FROM spaces WHERE id=?", (space_id,)).fetchone()
                if not space:
                    raise AppError("MAPPING_SPACE_NOT_FOUND", "Space was not found.", 404)
            elif space_name:
                space_id = stable_id("space", space_name.casefold())
                db.execute(
                    """
                    INSERT INTO spaces(id, name, created_ms, updated_ms) VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET updated_ms=excluded.updated_ms
                    """,
                    (space_id, space_name, timestamp, timestamp),
                )
                existing_space = db.execute("SELECT id FROM spaces WHERE name=?", (space_name,)).fetchone()
                space_id = existing_space[0]
            else:
                raise AppError("MAPPING_SPACE_REQUIRED", "Provide a space id or name.", 422)
            db.execute(
                "DELETE FROM source_channel_bindings WHERE source_channel_id=? AND valid_from_ms IS NULL",
                (source_channel_id,),
            )
            db.execute(
                """
                INSERT INTO source_channel_bindings(source_channel_id, space_id, clock_correction_ms, valid_from_ms, valid_to_ms)
                VALUES (?, ?, ?, NULL, NULL)
                """,
                (source_channel_id, space_id, correction),
            )
            db.execute(
                "DELETE FROM space_media_channels WHERE space_id=? AND role='primary' AND valid_from_ms IS NULL",
                (space_id,),
            )
            db.execute(
                """
                INSERT INTO space_media_channels(space_id, nvr_channel_id, role, priority, valid_from_ms, valid_to_ms)
                VALUES (?, ?, 'primary', 0, NULL, NULL)
                """,
                (space_id, media_channel_id),
            )
            db.execute(
                """
                UPDATE intervals SET
                    clock_correction_ms=?,
                    resolved_start_ms=raw_start_ms+?,
                    resolved_end_ms=raw_end_ms+?,
                    media_start_ms=CASE WHEN media_start_ms IS NULL THEN NULL ELSE media_start_ms-clock_correction_ms+? END,
                    media_end_ms=CASE WHEN media_end_ms IS NULL THEN NULL ELSE media_end_ms-clock_correction_ms+? END,
                    updated_ms=?
                WHERE source_channel_id=?
                """,
                (correction, correction, correction, correction, correction, timestamp, source_channel_id),
            )
        return next(row for row in self.list_source_channels() if row["id"] == source_channel_id)

    def _enqueue_job(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = new_id("job")
        timestamp = now_ms()
        self.database.execute(
            """
            INSERT INTO jobs(id, kind, state, payload_json, attempts, created_ms, updated_ms)
            VALUES (?, ?, 'queued', ?, 0, ?, ?)
            """,
            (job_id, kind, json.dumps(payload), timestamp, timestamp),
        )
        return self.get_job(job_id)

    def run_job(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(job["payload_json"])
        if job["kind"] == "recording_search":
            return self._run_search(job["id"], payload)
        if job["kind"] == "clip":
            return self._run_clip(job["id"], payload)
        if job["kind"] == "event_preview":
            return self._run_event_preview(job["id"], payload)
        if job["kind"] == "event_animation":
            return self._run_event_animation(job["id"], payload)
        if job["kind"] == "event_visual_analysis":
            return self._run_event_visual_analysis(job["id"], payload)
        if job["kind"] == "channel_snapshot":
            return self._run_channel_snapshot(job["id"], payload)
        raise AppError("JOB_KIND_UNSUPPORTED", "Job kind is not supported.", 500)

    def _run_search(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        nvr = self._nvr_row(payload["nvr_id"])
        adapter = self._adapter_for_row(nvr)
        timestamp = now_ms()
        source_id = stable_id("source", "nvr", nvr["id"])
        bookmark_ids: list[str] = []
        requested_event_types = tuple(payload.get("event_types") or (
            "motion", "video_tamper", "line_crossing", "region_intrusion",
        ))
        self.database.execute("DELETE FROM search_results WHERE search_job_id=?", (job_id,))
        channel_rows = [self._channel_row(channel_id) for channel_id in payload["channel_ids"]]
        if any(channel["nvr_id"] != nvr["id"] for channel in channel_rows):
            raise AppError("NVR_CHANNEL_SCOPE_INVALID", "A camera does not belong to this NVR.", 422)
        channels_by_external_id = {
            channel["external_channel_id"]: channel for channel in channel_rows
        }
        query = HistoricalEventQuery(
            tuple(channels_by_external_id),
            requested_event_types,
            from_utc_millis(payload["from_ms"]),
            from_utc_millis(payload["to_ms"]),
        )
        try:
            event_result = adapter.search_historical_events(query)
        except ValueError as exc:
            raise AppError("EVENT_SEARCH_FILTER_INVALID", str(exc), 422) from exc
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR historical event search failed.", 502) from exc
        if self._cancel_requested(job_id):
            raise AppError("JOB_CANCELLED", "Job was cancelled.", 409)
        with self.database.transaction() as db:
            db.execute(
                """
                INSERT INTO sources(id, kind, external_source_id, version, last_seen_ms)
                VALUES (?, 'nvr', ?, ?, ?)
                ON CONFLICT(kind, external_source_id) DO UPDATE SET last_seen_ms=excluded.last_seen_ms
                """,
                (source_id, nvr["id"], nvr["firmware"], timestamp),
            )
            for channel in channel_rows:
                source_channel_id = stable_id("source_channel", source_id, channel["external_channel_id"])
                db.execute(
                    """
                    INSERT INTO source_channels(id, source_id, external_key, label, kind, nvr_channel_id, created_ms, updated_ms)
                    VALUES (?, ?, ?, ?, 'nvr_event', ?, ?, ?)
                    ON CONFLICT(source_id, external_key) DO UPDATE SET
                        label=excluded.label, nvr_channel_id=excluded.nvr_channel_id, updated_ms=excluded.updated_ms
                    """,
                    (
                        source_channel_id,
                        source_id,
                        channel["external_channel_id"],
                        channel["alias"] or channel["device_name"],
                        channel["id"],
                        timestamp,
                        timestamp,
                    ),
                )
            for event in event_result.items:
                channel = channels_by_external_id.get(event.external_channel_id)
                if channel is None:
                    continue
                channel_id = channel["id"]
                source_channel_id = stable_id("source_channel", source_id, event.external_channel_id)
                start_ms = utc_millis(event.occurred_at)
                event_duration_ms = None
                if event.ended_at is not None:
                    paired_end_ms = utc_millis(event.ended_at)
                    if start_ms < paired_end_ms <= start_ms + 3_600_000:
                        event_duration_ms = paired_end_ms - start_ms
                end_ms = start_ms + (event_duration_ms or 1_000)
                interval_id = stable_id("interval", source_id, event.source_id)
                bookmark_ids.append(interval_id)
                db.execute(
                        """
                        INSERT INTO intervals(
                            id, source_id, source_event_id, source_channel_id, nvr_channel_id,
                            event_type, raw_start_ms, raw_end_ms, clock_correction_ms,
                            resolved_start_ms, resolved_end_ms, quality_gate, tags_json,
                            attributes_json, created_ms, updated_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'unknown', ?, ?, ?, ?)
                        ON CONFLICT(source_id, source_event_id) DO UPDATE SET
                            event_type=excluded.event_type,
                            raw_start_ms=excluded.raw_start_ms, raw_end_ms=excluded.raw_end_ms,
                            resolved_start_ms=excluded.resolved_start_ms, resolved_end_ms=excluded.resolved_end_ms,
                            attributes_json=excluded.attributes_json, updated_ms=excluded.updated_ms
                        """,
                        (
                            interval_id,
                            source_id,
                            event.source_id,
                            source_channel_id,
                            channel_id,
                            f"nvr.{event.event_type}",
                            start_ms,
                            end_ms,
                            start_ms,
                            end_ms,
                            json.dumps(["nvr_originated"]),
                            json.dumps(
                                {
                                    "hikvision": {
                                        "classification": event.classification,
                                        "canonical_event_type": event.event_type,
                                        "evidence_source": "historical_alarm_log",
                                        "area_name": payload.get("area_name") or None,
                                        "search_job_id": job_id,
                                        "event_duration_ms": event_duration_ms,
                                        "duration_source": (
                                            "paired_alarm_log"
                                            if event_duration_ms is not None
                                            else "unknown"
                                        ),
                                    }
                                }
                            ),
                            timestamp,
                            timestamp,
                        ),
                )
                db.execute(
                    "INSERT OR IGNORE INTO search_results(search_job_id, interval_id) VALUES (?, ?)",
                    (job_id, interval_id),
                )
        self.database.execute(
            "UPDATE jobs SET progress=1, updated_ms=? WHERE id=?", (now_ms(), job_id)
        )
        return {
            "bookmark_ids": bookmark_ids,
            "count": len(bookmark_ids),
            "truncated": event_result.truncated,
            "evidence_source": "historical_alarm_log",
        }

    def _run_event_preview(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._set_job_progress(job_id, 0.1)
        self.database.execute(
            "UPDATE event_previews SET status='generating', updated_ms=? WHERE interval_id=?",
            (now_ms(), payload["interval_id"]),
        )
        channel = self._channel_row(payload["channel_id"])
        nvr = self._nvr_row(channel["nvr_id"])
        if not channel["primary_track_id"]:
            raise AppError("CAPABILITY_PLAYBACK_TRACK_UNKNOWN", "Channel has no playback track identity.", 422)
        query = RecordingQuery(
            channel["external_channel_id"], channel["primary_track_id"],
            from_utc_millis(payload["start_ms"]), from_utc_millis(payload["end_ms"]),
        )
        adapter = self._adapter_for_row(nvr)
        self._set_job_progress(job_id, 0.3)
        try:
            spans = adapter.search_all_recordings(query)
            resolution = adapter.resolve_media(spans, query.start_at, query.end_at)
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR event preview could not be resolved.", 502) from exc
        if not resolution.playback_segments:
            raise AppError("RECORDING_NOT_FOUND", "No NVR recording covers the event preview.", 409)
        self._set_job_progress(job_id, 0.6)
        username, password = self.secret_store.get(nvr["secret_ref"])
        preview_id = stable_id("preview", payload["interval_id"])
        segment = resolution.playback_segments[0]
        path = self.media_runner.generate_preview(
            preview_id=preview_id,
            playback_locator=self._media_locator(
                segment.playback_locator, nvr, segment.start_at, segment.end_at
            ),
            username=username,
            password=password,
            cancel_requested=lambda: self._cancel_requested(job_id),
        )
        self._set_job_progress(job_id, 0.95)
        relative_path = path.resolve().relative_to(self.config.clip_dir.resolve()).as_posix()
        self.database.execute(
            "UPDATE event_previews SET status='ready', relative_path=?, updated_ms=? WHERE interval_id=?",
            (relative_path, now_ms(), payload["interval_id"]),
        )
        return {"interval_id": payload["interval_id"]}

    def _run_event_animation(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._set_job_progress(job_id, 0.1)
        self.database.execute(
            "UPDATE event_animations SET status='generating', updated_ms=? WHERE interval_id=?",
            (now_ms(), payload["interval_id"]),
        )
        channel = self._channel_row(payload["channel_id"])
        nvr = self._nvr_row(channel["nvr_id"])
        if not channel["primary_track_id"]:
            raise AppError("CAPABILITY_PLAYBACK_TRACK_UNKNOWN", "Channel has no playback track identity.", 422)
        query = RecordingQuery(
            channel["external_channel_id"], channel["primary_track_id"],
            from_utc_millis(payload["start_ms"]), from_utc_millis(payload["end_ms"]),
        )
        adapter = self._adapter_for_row(nvr)
        self._set_job_progress(job_id, 0.3)
        try:
            spans = adapter.search_all_recordings(query)
            resolution = adapter.resolve_media(spans, query.start_at, query.end_at)
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR hover preview could not be resolved.", 502) from exc
        if not resolution.playback_segments:
            raise AppError("RECORDING_NOT_FOUND", "No NVR recording covers the hover preview.", 409)
        self._set_job_progress(job_id, 0.6)
        username, password = self.secret_store.get(nvr["secret_ref"])
        segment = resolution.playback_segments[0]
        path = self.media_runner.generate_animation(
            animation_id=stable_id("animation", payload["interval_id"]),
            playback_locator=self._media_locator(
                segment.playback_locator, nvr, segment.start_at, segment.end_at
            ),
            username=username,
            password=password,
            duration_seconds=3,
            cancel_requested=lambda: self._cancel_requested(job_id),
        )
        self._set_job_progress(job_id, 0.95)
        relative_path = path.resolve().relative_to(self.config.clip_dir.resolve()).as_posix()
        self.database.execute(
            "UPDATE event_animations SET status='ready', relative_path=?, updated_ms=? WHERE interval_id=?",
            (relative_path, now_ms(), payload["interval_id"]),
        )
        return {"interval_id": payload["interval_id"]}

    def _run_event_visual_analysis(
        self, job_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        interval_id = payload["interval_id"]
        self._set_job_progress(job_id, 0.05)
        self.database.execute(
            "UPDATE event_visual_analyses SET status='analyzing', updated_ms=? WHERE interval_id=?",
            (now_ms(), interval_id),
        )
        channel = self._channel_row(payload["channel_id"])
        nvr = self._nvr_row(channel["nvr_id"])
        if not channel["primary_track_id"]:
            raise AppError(
                "CAPABILITY_PLAYBACK_TRACK_UNKNOWN", "Channel has no playback track identity.", 422
            )
        query = RecordingQuery(
            channel["external_channel_id"],
            channel["primary_track_id"],
            from_utc_millis(payload["start_ms"]),
            from_utc_millis(payload["end_ms"]),
        )
        adapter = self._adapter_for_row(nvr)
        self._set_job_progress(job_id, 0.20)
        try:
            spans = adapter.search_all_recordings(query)
            resolution = adapter.resolve_media(spans, query.start_at, query.end_at)
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR visual-analysis media could not be resolved.", 502) from exc
        if not resolution.playback_segments:
            raise AppError(
                "RECORDING_NOT_FOUND", "No NVR recording covers the visual-analysis window.", 409
            )
        segment = next(
            (
                candidate for candidate in resolution.playback_segments
                if utc_millis(candidate.start_at) <= payload["start_ms"] < utc_millis(candidate.end_at)
            ),
            resolution.playback_segments[0],
        )
        sample_start_ms = max(payload["start_ms"], utc_millis(segment.start_at))
        sample_end_ms = min(payload["end_ms"], utc_millis(segment.end_at))
        if sample_end_ms <= sample_start_ms:
            raise AppError(
                "RECORDING_GAP", "The visual-analysis event window is not continuously covered.", 409
            )
        username, password = self.secret_store.get(nvr["secret_ref"])
        playback_locator = self._media_locator(
            segment.playback_locator,
            nvr,
            from_utc_millis(sample_start_ms),
            from_utc_millis(sample_end_ms),
        )
        self._set_job_progress(job_id, 0.35)
        frames = self.media_runner.sample_bgr_frames(
            playback_locator=playback_locator,
            username=username,
            password=password,
            duration_seconds=(sample_end_ms - sample_start_ms) / 1_000,
            width=416,
            height=416,
            fps=5,
            cancel_requested=lambda: self._cancel_requested(job_id),
        )
        self._set_job_progress(job_id, 0.65)
        try:
            analysis = self.visual_analyzer.analyze(
                frames=frames.frames,
                width=frames.width,
                height=frames.height,
                fps=frames.fps,
                event_type=payload["event_type"],
                overlays=payload.get("overlays") or [],
            )
        except VisionError as exc:
            raise AppError(exc.code, exc.message, 422) from exc
        result = analysis.as_dict()
        result["analysis_signature"] = payload["analysis_signature"]
        result["analyzed_window"] = {
            "start_at": rfc3339(sample_start_ms),
            "end_at": rfc3339(sample_end_ms),
        }
        result["trigger_at"] = (
            rfc3339(sample_start_ms + analysis.trigger_offset_ms)
            if analysis.trigger_offset_ms is not None else None
        )
        result["evidence_animation_ready"] = False
        if analysis.verdict == "confirmed_trigger" and analysis.trigger_offset_ms is not None:
            trigger_ms = sample_start_ms + analysis.trigger_offset_ms
            evidence_start_ms = max(sample_start_ms, trigger_ms - 1_000)
            evidence_end_ms = min(sample_end_ms, trigger_ms + 4_000)
            if evidence_end_ms - evidence_start_ms >= 1_000:
                try:
                    evidence_path = self.media_runner.generate_animation(
                        animation_id=stable_id("animation", interval_id),
                        playback_locator=self._media_locator(
                            segment.playback_locator,
                            nvr,
                            from_utc_millis(evidence_start_ms),
                            from_utc_millis(evidence_end_ms),
                        ),
                        username=username,
                        password=password,
                        duration_seconds=(evidence_end_ms - evidence_start_ms) / 1_000,
                        cancel_requested=lambda: self._cancel_requested(job_id),
                    )
                    relative_path = evidence_path.resolve().relative_to(
                        self.config.clip_dir.resolve()
                    ).as_posix()
                    timestamp = now_ms()
                    self.database.execute(
                        """
                        INSERT INTO event_animations(
                            interval_id, job_id, status, relative_path, created_ms, updated_ms
                        ) VALUES (?, ?, 'ready', ?, ?, ?)
                        ON CONFLICT(interval_id) DO UPDATE SET job_id=excluded.job_id,
                            status='ready', relative_path=excluded.relative_path,
                            updated_ms=excluded.updated_ms
                        """,
                        (interval_id, job_id, relative_path, timestamp, timestamp),
                    )
                    result["evidence_animation_ready"] = True
                except MediaError:
                    result["evidence_animation_ready"] = False
        self._set_job_progress(job_id, 0.95)
        self.database.execute(
            """
            UPDATE event_visual_analyses
            SET status='ready', verdict=?, result_json=?, updated_ms=?
            WHERE interval_id=?
            """,
            (analysis.verdict, json.dumps(result), now_ms(), interval_id),
        )
        return {"interval_id": interval_id, **result}

    def _run_channel_snapshot(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        cached = self.database.one(
            "SELECT relative_path FROM channel_snapshots WHERE channel_id=?",
            (payload["channel_id"],),
        )
        if not cached or not self._derived_path_exists(cached["relative_path"]):
            self.database.execute(
                "UPDATE channel_snapshots SET status='generating', updated_ms=? WHERE channel_id=?",
                (now_ms(), payload["channel_id"]),
            )
        channel = self._channel_row(payload["channel_id"])
        nvr = self._nvr_row(channel["nvr_id"])
        tracks = json.loads(channel["metadata_json"]).get("stream_track_ids") or []
        track_id = tracks[-1] if tracks else channel["primary_track_id"]
        if not track_id or not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", track_id):
            raise AppError("CAPABILITY_LIVE_TRACK_UNKNOWN", "Camera has no evidenced live stream identity.", 422)
        username, password = self.secret_store.get(nvr["secret_ref"])
        last_error: MediaError | None = None
        path = None
        snapshot_source = "live_low_rate"
        for live_path in (f"/Streaming/Channels/{track_id}", f"/ISAPI/Streaming/channels/{track_id}"):
            live_locator = urlunsplit(("rtsp", f"{nvr['host']}:554", live_path, "", ""))
            try:
                path = self.media_runner.generate_snapshot(
                    snapshot_id=stable_id("snapshot", payload["channel_id"]),
                    live_locator=live_locator,
                    username=username,
                    password=password,
                    cancel_requested=lambda: self._cancel_requested(job_id),
                )
                break
            except MediaError as exc:
                last_error = exc
        if path is None:
            snapshot_source = "recent_recording"
            end_ms = now_ms()
            query = RecordingQuery(
                channel["external_channel_id"], channel["primary_track_id"],
                from_utc_millis(end_ms - 10 * 60_000), from_utc_millis(end_ms),
            )
            adapter = self._adapter_for_row(nvr)
            try:
                spans = adapter.search_all_recordings(query)
            except HikvisionError as exc:
                if last_error is not None:
                    raise last_error
                raise AppError(exc.code, "A recent camera image could not be resolved.", 502) from exc
            if not spans:
                if last_error is not None:
                    raise last_error
                raise AppError("RECORDING_NOT_FOUND", "No recent recording is available for this camera.", 409)
            latest = max(spans, key=lambda span: span.end_at)
            path = self.media_runner.generate_snapshot(
                snapshot_id=stable_id("snapshot", payload["channel_id"]),
                live_locator=self._media_locator(latest.playback_locator, nvr),
                username=username,
                password=password,
                cancel_requested=lambda: self._cancel_requested(job_id),
            )
        relative_path = path.resolve().relative_to(self.config.clip_dir.resolve()).as_posix()
        captured = now_ms()
        self.database.execute(
            """
            UPDATE channel_snapshots SET status='ready', relative_path=?, captured_ms=?,
                expires_ms=?, updated_ms=? WHERE channel_id=?
            """,
            (
                relative_path,
                captured,
                captured + CHANNEL_SNAPSHOT_TTL_MS,
                captured,
                payload["channel_id"],
            ),
        )
        return {"channel_id": payload["channel_id"], "source": snapshot_source}

    def _run_clip(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._set_job_progress(job_id, 0.08)
        channel = self._channel_row(payload["channel_id"])
        nvr = self._nvr_row(channel["nvr_id"])
        if not channel["primary_track_id"]:
            raise AppError("CAPABILITY_PLAYBACK_TRACK_UNKNOWN", "Channel has no playback track identity.", 422)
        self.database.execute("UPDATE clips SET status='generating' WHERE id=?", (payload["clip_id"],))
        query = RecordingQuery(
            channel["external_channel_id"],
            channel["primary_track_id"],
            from_utc_millis(payload["start_ms"]),
            from_utc_millis(payload["end_ms"]),
        )
        adapter = self._adapter_for_row(nvr)
        self._set_job_progress(job_id, 0.25)
        try:
            spans = adapter.search_all_recordings(query)
            resolution = adapter.resolve_media(spans, query.start_at, query.end_at)
        except HikvisionError as exc:
            raise AppError(exc.code, "NVR media could not be resolved.", 502) from exc
        if not resolution.complete:
            raise AppError(
                "RECORDING_GAP",
                "The NVR does not cover the complete requested time window.",
                409,
                {"coverage": "partial", "missing_spans": jsonable(resolution.missing_spans)},
            )
        self._set_job_progress(job_id, 0.5)
        username, password = self.secret_store.get(nvr["secret_ref"])
        result = self.media_runner.generate(
            clip_id=payload["clip_id"],
            playback_locators=tuple(
                self._media_locator(
                    segment.playback_locator, nvr, segment.start_at, segment.end_at
                )
                for segment in resolution.playback_segments
            ),
            username=username,
            password=password,
            audio_policy=payload["audio_policy"],
            max_duration_seconds=(payload["end_ms"] - payload["start_ms"]) / 1000,
            cancel_requested=lambda: self._cancel_requested(job_id),
        )
        self._set_job_progress(job_id, 0.92)
        if self._cancel_requested(job_id):
            result.path.unlink(missing_ok=True)
            raise AppError("JOB_CANCELLED", "Job was cancelled.", 409)
        relative_path = result.path.resolve().relative_to(self.config.clip_dir.resolve()).as_posix()
        self.database.execute(
            """
            UPDATE clips SET status='ready', actual_start_ms=?, actual_end_ms=?, relative_path=?,
                video_codec=?, audio_codec=?, size_bytes=?, accessed_ms=? WHERE id=?
            """,
            (
                payload["start_ms"],
                payload["end_ms"],
                relative_path,
                result.video_codec,
                result.audio_codec,
                result.size_bytes,
                now_ms(),
                payload["clip_id"],
            ),
        )
        self._enforce_clip_quota(payload["clip_id"])
        return {"clip_id": payload["clip_id"]}

    def _enforce_clip_quota(self, preserve_clip_id: str) -> None:
        quota = int(self.database.settings()["clip_quota_bytes"])
        rows = self.database.all(
            "SELECT id, relative_path, size_bytes FROM clips WHERE status='ready' ORDER BY accessed_ms ASC"
        )
        total = sum(int(row["size_bytes"] or 0) for row in rows)
        for row in rows:
            if total <= quota:
                break
            if row["id"] == preserve_clip_id:
                continue
            path = (self.config.clip_dir / row["relative_path"]).resolve()
            if path.parent != self.config.clip_dir.resolve():
                continue
            size = int(row["size_bytes"] or 0)
            self.database.execute("DELETE FROM clips WHERE id=?", (row["id"],))
            path.unlink(missing_ok=True)
            total -= size

    def _mapped_media_channel(self, interval: dict[str, Any]) -> str:
        row = self.database.one(
            """
            SELECT smc.nvr_channel_id
            FROM source_channel_bindings b
            JOIN space_media_channels smc ON smc.space_id=b.space_id AND smc.valid_to_ms IS NULL
            WHERE b.source_channel_id=? AND b.valid_to_ms IS NULL
            ORDER BY CASE smc.role WHEN 'primary' THEN 0 ELSE 1 END, smc.priority
            LIMIT 1
            """,
            (interval["source_channel_id"],),
        )
        if not row:
            raise AppError("MAPPING_REQUIRED", "Source channel is not mapped to an NVR channel.", 409)
        return row["nvr_channel_id"]

    def _cancel_requested(self, job_id: str) -> bool:
        row = self.database.one("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,))
        return bool(row and row["cancel_requested"])

    def _adapter_for_row(self, row: dict[str, Any]) -> HikvisionAdapter:
        username, password = self.secret_store.get(row["secret_ref"])
        connection = ConnectionConfig(
            host=row["host"],
            username=username,
            password=password,
            http_port=row["http_port"],
            use_https=bool(row["use_https"]),
            verify_tls=bool(row["verify_tls"]),
        )
        return self.adapter_factory(connection)

    @staticmethod
    def _media_locator(
        locator: str,
        nvr: dict[str, Any],
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> str:
        if start_at is not None and end_at is not None:
            locator = playback_locator_for_window(locator, start_at, end_at)
        offset = nvr.get("utc_offset_minutes")
        if offset is None:
            match = re.fullmatch(r"CST([+-])(\d{1,2}):?(\d{2})?:?(\d{2})?", str(nvr.get("timezone") or ""))
            if match:
                minutes = int(match.group(2)) * 60 + int(match.group(3) or 0)
                offset = minutes if match.group(1) == "-" else -minutes
            else:
                offset = 0
        return playback_locator_for_device_time(locator, int(offset))

    @staticmethod
    def _connection_from_values(values: dict[str, Any]) -> ConnectionConfig:
        host = str(values.get("host", "")).strip()
        username = str(values.get("username", "")).strip()
        password = str(values.get("password", ""))
        if not host or any(character in host for character in "/@?#"):
            raise AppError("NVR_ADDRESS_INVALID", "NVR host is invalid.", 422)
        if not username or not password:
            raise AppError("AUTH_CREDENTIALS_REQUIRED", "NVR username and password are required.", 422)
        port = int(values.get("http_port", 443 if values.get("use_https") else 80))
        if not 1 <= port <= 65535:
            raise AppError("NVR_PORT_INVALID", "NVR port is invalid.", 422)
        return ConnectionConfig(
            host=host,
            username=username,
            password=password,
            http_port=port,
            use_https=bool(values.get("use_https", False)),
            verify_tls=bool(values.get("verify_tls", True)),
        )

    def _nvr_row(self, nvr_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM nvrs WHERE id=?", (nvr_id,))
        if not row:
            raise AppError("NVR_NOT_FOUND", "NVR was not found.", 404)
        return row

    def _channel_row(self, channel_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM nvr_channels WHERE id=?", (channel_id,))
        if not row:
            raise AppError("NVR_CHANNEL_NOT_FOUND", "NVR channel was not found.", 404)
        return row

    def _trace_session_row(self, session_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM trace_sessions WHERE id=?", (session_id,))
        if not row:
            raise AppError("TRACE_SESSION_NOT_FOUND", "Trace session was not found.", 404)
        return row

    @staticmethod
    def _store_capabilities(db: Any, nvr_id: str, capabilities: tuple[Any, ...]) -> None:
        for capability in capabilities:
            db.execute(
                """
                INSERT INTO nvr_capabilities(nvr_id, capability, status, evidence_json, observed_ms)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(nvr_id, capability) DO UPDATE SET
                    status=excluded.status, evidence_json=excluded.evidence_json, observed_ms=excluded.observed_ms
                """,
                (
                    nvr_id,
                    capability.capability,
                    capability.state,
                    json.dumps(
                        {
                            "endpoint": capability.endpoint,
                            "status_code": capability.status_code,
                            "fixture_hash": capability.fixture_hash,
                            "note": capability.note,
                        }
                    ),
                    utc_millis(capability.observed_at),
                ),
            )

    @staticmethod
    def _public_nvr(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "host": row["host"],
            "http_port": row["http_port"],
            "use_https": bool(row["use_https"]),
            "verify_tls": bool(row["verify_tls"]),
            "model": row["model"],
            "firmware": row["firmware"],
            "timezone": row["timezone"],
            "clock_skew_ms": row["clock_skew_ms"],
            "utc_offset_minutes": row.get("utc_offset_minutes"),
            "created_at": rfc3339(row["created_ms"]),
            "updated_at": rfc3339(row["updated_ms"]),
        }

    @staticmethod
    def _public_channel(row: dict[str, Any]) -> dict[str, Any]:
        metadata = json.loads(row["metadata_json"])
        return {
            "id": row["id"],
            "nvr_id": row["nvr_id"],
            "external_channel_id": row["external_channel_id"],
            "primary_track_id": row["primary_track_id"],
            "stream_track_ids": metadata.get("stream_track_ids", []),
            "device_name": row["device_name"],
            "alias": row["alias"],
            "online": bool(row["online"]),
        }

    def _public_trace_session(self, row: dict[str, Any]) -> dict[str, Any]:
        iterations: list[dict[str, Any]] = []
        for iteration in self.database.all(
            "SELECT * FROM trace_iterations WHERE session_id=? ORDER BY from_ms DESC, created_ms DESC",
            (row["id"],),
        ):
            jobs = [
                self._public_job(job)
                for job in self.database.all(
                    """
                    SELECT j.* FROM trace_iteration_jobs tij
                    JOIN jobs j ON j.id=tij.job_id
                    WHERE tij.iteration_id=? ORDER BY j.created_ms, j.id
                    """,
                    (iteration["id"],),
                )
            ]
            count = self.database.one(
                """
                SELECT COUNT(DISTINCT sr.interval_id) AS total
                FROM trace_iteration_jobs tij
                JOIN search_results sr ON sr.search_job_id=tij.job_id
                WHERE tij.iteration_id=?
                """,
                (iteration["id"],),
            )
            states = {job["state"] for job in jobs}
            if states.intersection({"queued", "running"}):
                state = "running"
            elif states == {"succeeded"}:
                state = "succeeded"
            elif states and states.issubset({"failed", "cancelled", "interrupted"}):
                state = "failed"
            else:
                state = "partial"
            iterations.append(
                {
                    "id": iteration["id"],
                    "label": iteration["label"],
                    "from": rfc3339(iteration["from_ms"]),
                    "to": rfc3339(iteration["to_ms"]),
                    "state": state,
                    "result_count": int(count["total"] if count else 0),
                    "jobs": jobs,
                    "created_at": rfc3339(iteration["created_ms"]),
                }
            )
        total = self.database.one(
            """
            SELECT COUNT(DISTINCT sr.interval_id) AS total
            FROM trace_iterations ti
            JOIN trace_iteration_jobs tij ON tij.iteration_id=ti.id
            JOIN search_results sr ON sr.search_job_id=tij.job_id
            WHERE ti.session_id=?
            """,
            (row["id"],),
        )
        return {
            "id": row["id"],
            "channel_ids": json.loads(row["channel_ids_json"]),
            "event_types": json.loads(row["event_types_json"]),
            "preset_id": row["preset_id"],
            "iterations": iterations,
            "result_count": int(total["total"] if total else 0),
            "created_at": rfc3339(row["created_ms"]),
            "updated_at": rfc3339(row["updated_ms"]),
        }

    def _public_interval(self, row: dict[str, Any]) -> dict[str, Any]:
        analysis = self.database.one(
            "SELECT * FROM event_visual_analyses WHERE interval_id=?", (row["id"],)
        )
        return {
            "id": row["id"],
            "source": {
                "id": row["source_id"],
                "kind": row["source_kind"],
                "external_id": row["external_source_id"],
            },
            "source_channel": {
                "id": row["source_channel_id"],
                "label": row["source_channel_label"],
                "kind": row["source_channel_kind"],
            },
            "media_channel_id": row["nvr_channel_id"],
            "media_channel_label": row["media_channel_label"],
            "event_type": row["event_type"],
            "raw_start_at": rfc3339(row["raw_start_ms"]),
            "raw_end_at": rfc3339(row["raw_end_ms"]),
            "clock_correction_ms": row["clock_correction_ms"],
            "start_at": rfc3339(row["resolved_start_ms"]),
            "end_at": rfc3339(row["resolved_end_ms"]),
            "quality": {"gate": row["quality_gate"] or "unknown", "score": row["quality_score"]},
            "confidence": row["confidence"],
            "media_window": {
                "start_at": rfc3339(row["media_start_ms"]),
                "end_at": rfc3339(row["media_end_ms"]),
            } if row["media_start_ms"] is not None else None,
            "tags": json.loads(row["tags_json"]),
            "attributes": json.loads(row["attributes_json"]),
            "visual_analysis": (
                self._public_event_visual_analysis(analysis) if analysis else None
            ),
        }

    def _public_event_visual_analysis(self, row: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(row["result_json"]) if row.get("result_json") else None
        return {
            "bookmark_id": row["interval_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "progress": self._job_progress(row["job_id"]),
            "verdict": row.get("verdict"),
            "result": result,
            "evidence_content_url": (
                f"/api/v1/bookmarks/{row['interval_id']}/animation/content"
                if result and result.get("evidence_animation_ready") else None
            ),
        }

    @staticmethod
    def _public_job(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "state": row["state"],
            "progress": row["progress"],
            "error": {
                "code": row["error_code"],
                "message": row["error_message"],
                "details": json.loads(row["error_details_json"] or "{}"),
            } if row["error_code"] else None,
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "attempts": row["attempts"],
            "created_at": rfc3339(row["created_ms"]),
            "started_at": rfc3339(row["started_ms"]),
            "finished_at": rfc3339(row["finished_ms"]),
        }

    def _public_clip(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "job_id": row["job_id"],
            "channel_id": row["nvr_channel_id"],
            "requested_window": {
                "start_at": rfc3339(row["requested_start_ms"]),
                "end_at": rfc3339(row["requested_end_ms"]),
            },
            "actual_window": {
                "start_at": rfc3339(row["actual_start_ms"]),
                "end_at": rfc3339(row["actual_end_ms"]),
            } if row["actual_start_ms"] is not None else None,
            "status": row["status"],
            "progress": self._job_progress(row["job_id"]),
            "video_codec": row["video_codec"],
            "audio_codec": row["audio_codec"],
            "size_bytes": row["size_bytes"],
            "created_at": rfc3339(row["created_ms"]),
            "content_url": f"/api/v1/clips/{row['id']}/content" if row["status"] == "ready" else None,
            "origin": json.loads(row["origin_json"]) if row.get("origin_json") else None,
        }

    def _public_event_preview(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "bookmark_id": row["interval_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "progress": self._job_progress(row["job_id"]),
            "content_url": (
                f"/api/v1/bookmarks/{row['interval_id']}/preview/content"
                if row["status"] == "ready" else None
            ),
        }

    def _public_event_animation(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "bookmark_id": row["interval_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "progress": self._job_progress(row["job_id"]),
            "content_url": (
                f"/api/v1/bookmarks/{row['interval_id']}/animation/content"
                if row["status"] == "ready" else None
            ),
        }

    def _public_channel_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        cache_ready = bool(
            row["relative_path"] and self._derived_path_exists(row["relative_path"])
        )
        job = (
            self.database.one("SELECT state, result_json FROM jobs WHERE id=?", (row["job_id"],))
            if row["job_id"] else None
        )
        refreshing = bool(job and job["state"] in {"queued", "running"})
        effective_status = "ready" if cache_ready else row["status"]
        return {
            "channel_id": row["channel_id"],
            "job_id": row["job_id"],
            "status": effective_status,
            "captured_at": rfc3339(row["captured_ms"]),
            "expires_at": rfc3339(row["expires_ms"]),
            "stale": bool(cache_ready and int(row["expires_ms"] or 0) <= now_ms()),
            "refreshing": refreshing,
            "source": (
                json.loads(job["result_json"]).get("source")
                if job and job["result_json"] else None
            ),
            "content_url": (
                f"/api/v1/channels/{row['channel_id']}/snapshot/content"
                if cache_ready else None
            ),
        }

    @staticmethod
    def _public_search_preset(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "nvr_id": row["nvr_id"],
            "area_name": row["area_name"],
            "channel_ids": json.loads(row.get("scope_json") or row["channel_ids_json"]),
            "event_types": json.loads(row["event_types_json"]),
            "created_at": rfc3339(row["created_ms"]),
            "updated_at": rfc3339(row["updated_ms"]),
            "last_used_at": rfc3339(row["last_used_ms"]),
        }

    @staticmethod
    def _external_time(value: str, name: str) -> int:
        try:
            from tracecue_engine import parse_rfc3339
            return utc_millis(parse_rfc3339(value, name))
        except Exception as exc:
            raise AppError("TIMELINE_TIMESTAMP_INVALID", f"{name} must be RFC 3339 with an explicit offset.", 422) from exc


class JobWorker:
    def __init__(self, services: DesktopServices):
        self.services = services
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if any(thread.is_alive() for thread in self._threads):
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._loop,
                name=f"tracecue-jobs-{index + 1}",
                daemon=True,
            )
            for index in range(JOB_WORKER_COUNT)
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self._threads = []

    def process_once(self) -> bool:
        job = self._claim()
        if not job:
            return False
        try:
            result = self.services.run_job(job)
        except AppError as exc:
            state = "cancelled" if exc.code == "JOB_CANCELLED" else "failed"
            self._finish(job["id"], state, error=exc)
            if job["kind"] == "clip":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE clips SET status='failed' WHERE id=?", (payload["clip_id"],)
                )
            if job["kind"] == "event_preview":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_previews SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "event_animation":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_animations SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "event_visual_analysis":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_visual_analyses SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "channel_snapshot":
                self._mark_snapshot_failed(job)
        except BaseException:
            self._finish(
                job["id"],
                "failed",
                error=AppError("JOB_INTERNAL_ERROR", "The job failed unexpectedly.", 500),
            )
            if job["kind"] == "clip":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE clips SET status='failed' WHERE id=?", (payload["clip_id"],)
                )
            if job["kind"] == "event_preview":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_previews SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "event_animation":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_animations SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "event_visual_analysis":
                payload = json.loads(job["payload_json"])
                self.services.database.execute(
                    "UPDATE event_visual_analyses SET status='failed', updated_ms=? WHERE interval_id=?",
                    (now_ms(), payload["interval_id"]),
                )
            if job["kind"] == "channel_snapshot":
                self._mark_snapshot_failed(job)
        else:
            self._finish(job["id"], "succeeded", result=result)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.process_once():
                self._stop.wait(self.services.config.job_poll_seconds)

    def _claim(self) -> dict[str, Any] | None:
        timestamp = now_ms()
        with self.services.database.transaction() as db:
            row = db.execute(
                """
                SELECT * FROM jobs
                WHERE state='queued' AND cancel_requested=0
                ORDER BY CASE WHEN kind='channel_snapshot' THEN 1 ELSE 0 END,
                         created_ms, id
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            db.execute(
                """
                UPDATE jobs SET state='running', attempts=attempts+1, started_ms=?, updated_ms=?
                WHERE id=? AND state='queued'
                """,
                (timestamp, timestamp, row["id"]),
            )
            return dict(row)

    def _mark_snapshot_failed(self, job: dict[str, Any]) -> None:
        payload = json.loads(job["payload_json"])
        row = self.services.database.one(
            "SELECT relative_path FROM channel_snapshots WHERE channel_id=?",
            (payload["channel_id"],),
        )
        if row and self.services._derived_path_exists(row["relative_path"]):
            self.services.database.execute(
                "UPDATE channel_snapshots SET status='ready', updated_ms=? WHERE channel_id=?",
                (now_ms(), payload["channel_id"]),
            )
            return
        self.services.database.execute(
            "UPDATE channel_snapshots SET status='failed', updated_ms=? WHERE channel_id=?",
            (now_ms(), payload["channel_id"]),
        )

    def _finish(
        self,
        job_id: str,
        state: str,
        *,
        result: dict[str, Any] | None = None,
        error: AppError | None = None,
    ) -> None:
        timestamp = now_ms()
        self.services.database.execute(
            """
            UPDATE jobs SET state=?, progress=CASE WHEN ?='succeeded' THEN 1 ELSE progress END,
                result_json=?, error_code=?, error_message=?, error_details_json=?,
                finished_ms=?, updated_ms=? WHERE id=?
            """,
            (
                state,
                state,
                json.dumps(result) if result else None,
                error.code if error else None,
                error.message if error else None,
                json.dumps(error.details) if error else None,
                timestamp,
                timestamp,
                job_id,
            ),
        )
