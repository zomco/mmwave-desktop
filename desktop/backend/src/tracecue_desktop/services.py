"""Desktop application services and persistent background job execution."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tracecue_engine import dump_timeline, from_utc_millis, inspect_timeline, utc_millis
from tracecue_hikvision import (
    ConnectionConfig,
    DigestTransport,
    HikvisionAdapter,
    HikvisionError,
    RecordingQuery,
)

from .config import AppConfig
from .database import Database
from .errors import AppError, MediaError
from .media import FFmpegRunner
from .secrets import SecretStore, WindowsDpapiSecretStore


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
        self.worker = JobWorker(self)

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
                        timezone, clock_skew_ms, secret_ref, created_ms, updated_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        clip_rows = self.database.all(
            """
            SELECT c.relative_path FROM clips c
            JOIN nvr_channels nc ON nc.id=c.nvr_channel_id
            WHERE nc.nvr_id=? AND c.relative_path IS NOT NULL
            """,
            (nvr_id,),
        )
        self.database.execute("DELETE FROM nvrs WHERE id=?", (nvr_id,))
        self.secret_store.delete(row["secret_ref"])
        for clip in clip_rows:
            path = (self.config.clip_dir / clip["relative_path"]).resolve()
            if path.parent == self.config.clip_dir.resolve():
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

    def enqueue_search(self, values: dict[str, Any]) -> dict[str, Any]:
        nvr_id = values["nvr_id"]
        self._nvr_row(nvr_id)
        channel_ids = values.get("channel_ids") or []
        if not channel_ids:
            raise AppError("NVR_CHANNEL_REQUIRED", "At least one NVR channel is required.", 422)
        start_ms = self._external_time(values["from"], "from")
        end_ms = self._external_time(values["to"], "to")
        if end_ms <= start_ms:
            raise AppError("TIMELINE_RANGE_INVALID", "Search end must be after start.", 422)
        for channel_id in channel_ids:
            channel = self._channel_row(channel_id)
            if channel["nvr_id"] != nvr_id:
                raise AppError("NVR_CHANNEL_MISMATCH", "A channel does not belong to the selected NVR.", 422)
        return self._enqueue_job(
            "recording_search",
            {
                "nvr_id": nvr_id,
                "channel_ids": channel_ids,
                "from_ms": start_ms,
                "to_ms": end_ms,
                "source_modes": values.get("source_modes") or ["record_classification"],
            },
        )

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
            start_ms = interval["media_start_ms"] if interval["media_start_ms"] is not None else interval["resolved_start_ms"] - pre
            end_ms = interval["media_end_ms"] if interval["media_end_ms"] is not None else interval["resolved_end_ms"] + post
        else:
            channel_id = values.get("channel_id")
            if not channel_id or not values.get("from") or not values.get("to"):
                raise AppError("MEDIA_REQUEST_INVALID", "Provide a bookmark or an explicit channel and time window.", 422)
            start_ms = self._external_time(values["from"], "from")
            end_ms = self._external_time(values["to"], "to")
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
                                  status, created_ms, accessed_ms)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (clip_id, job_id, channel_id, start_ms, end_ms, timestamp, timestamp),
            )
        return self.get_clip(clip_id)

    def list_clips(self) -> list[dict[str, Any]]:
        return [self._public_clip(row) for row in self.database.all("SELECT * FROM clips ORDER BY created_ms DESC")]

    def get_clip(self, clip_id: str) -> dict[str, Any]:
        row = self.database.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row:
            raise AppError("MEDIA_CLIP_NOT_FOUND", "Clip was not found.", 404)
        return self._public_clip(row)

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
            "source_summary": source_summary,
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
        raise AppError("JOB_KIND_UNSUPPORTED", "Job kind is not supported.", 500)

    def _run_search(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        nvr = self._nvr_row(payload["nvr_id"])
        adapter = self._adapter_for_row(nvr)
        timestamp = now_ms()
        source_id = stable_id("source", "nvr", nvr["id"])
        bookmark_ids: list[str] = []
        with self.database.transaction() as db:
            db.execute(
                """
                INSERT INTO sources(id, kind, external_source_id, version, last_seen_ms)
                VALUES (?, 'nvr', ?, ?, ?)
                ON CONFLICT(kind, external_source_id) DO UPDATE SET last_seen_ms=excluded.last_seen_ms
                """,
                (source_id, nvr["id"], nvr["firmware"], timestamp),
            )
        for index, channel_id in enumerate(payload["channel_ids"]):
            if self._cancel_requested(job_id):
                raise AppError("JOB_CANCELLED", "Job was cancelled.", 409)
            channel = self._channel_row(channel_id)
            if not channel["primary_track_id"]:
                raise AppError("CAPABILITY_PLAYBACK_TRACK_UNKNOWN", "Channel has no playback track identity.", 422)
            query = RecordingQuery(
                channel["external_channel_id"],
                channel["primary_track_id"],
                from_utc_millis(payload["from_ms"]),
                from_utc_millis(payload["to_ms"]),
            )
            try:
                spans = adapter.search_all_recordings(query)
            except HikvisionError as exc:
                raise AppError(exc.code, "NVR recording search failed.", 502) from exc
            source_channel_id = stable_id("source_channel", source_id, channel["external_channel_id"])
            with self.database.transaction() as db:
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
                        channel_id,
                        timestamp,
                        timestamp,
                    ),
                )
                for span in spans:
                    start_ms = utc_millis(span.start_at)
                    end_ms = utc_millis(span.end_at)
                    source_event_id = span.source_id or hashlib.sha256(
                        f"{channel_id}|{start_ms}|{end_ms}|{span.classification}".encode()
                    ).hexdigest()[:24]
                    interval_id = stable_id("interval", source_id, source_event_id)
                    bookmark_ids.append(interval_id)
                    db.execute(
                        """
                        INSERT INTO intervals(
                            id, source_id, source_event_id, source_channel_id, nvr_channel_id,
                            event_type, raw_start_ms, raw_end_ms, clock_correction_ms,
                            resolved_start_ms, resolved_end_ms, quality_gate, tags_json,
                            attributes_json, created_ms, updated_ms
                        ) VALUES (?, ?, ?, ?, ?, 'nvr.recording', ?, ?, 0, ?, ?, 'unknown', ?, ?, ?, ?)
                        ON CONFLICT(source_id, source_event_id) DO UPDATE SET
                            raw_start_ms=excluded.raw_start_ms, raw_end_ms=excluded.raw_end_ms,
                            resolved_start_ms=excluded.resolved_start_ms, resolved_end_ms=excluded.resolved_end_ms,
                            attributes_json=excluded.attributes_json, updated_ms=excluded.updated_ms
                        """,
                        (
                            interval_id,
                            source_id,
                            source_event_id,
                            source_channel_id,
                            channel_id,
                            start_ms,
                            end_ms,
                            start_ms,
                            end_ms,
                            json.dumps(["nvr_originated"]),
                            json.dumps({"hikvision": {"classification": span.classification}}),
                            timestamp,
                            timestamp,
                        ),
                    )
                    db.execute(
                        """
                        INSERT OR REPLACE INTO recording_spans(
                            id, nvr_channel_id, start_ms, end_ms, classification,
                            locator_json, observed_ms, expires_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            stable_id("recording", channel_id, source_event_id),
                            channel_id,
                            start_ms,
                            end_ms,
                            span.classification,
                            json.dumps({"playback_locator": span.playback_locator}),
                            timestamp,
                            timestamp + 5 * 60 * 1000,
                        ),
                    )
            self.database.execute(
                "UPDATE jobs SET progress=?, updated_ms=? WHERE id=?",
                ((index + 1) / len(payload["channel_ids"]), now_ms(), job_id),
            )
        return {"bookmark_ids": bookmark_ids, "count": len(bookmark_ids)}

    def _run_clip(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
        username, password = self.secret_store.get(nvr["secret_ref"])
        result = self.media_runner.generate(
            clip_id=payload["clip_id"],
            playback_locators=resolution.playback_locators,
            username=username,
            password=password,
            audio_policy=payload["audio_policy"],
            cancel_requested=lambda: self._cancel_requested(job_id),
        )
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

    @staticmethod
    def _public_interval(row: dict[str, Any]) -> dict[str, Any]:
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

    @staticmethod
    def _public_clip(row: dict[str, Any]) -> dict[str, Any]:
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
            "video_codec": row["video_codec"],
            "audio_codec": row["audio_codec"],
            "size_bytes": row["size_bytes"],
            "created_at": rfc3339(row["created_ms"]),
            "content_url": f"/api/v1/clips/{row['id']}/content" if row["status"] == "ready" else None,
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
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tracecue-jobs", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

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
        except BaseException:
            self._finish(
                job["id"],
                "failed",
                error=AppError("JOB_INTERNAL_ERROR", "The job failed unexpectedly.", 500),
            )
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
                "SELECT * FROM jobs WHERE state='queued' AND cancel_requested=0 ORDER BY created_ms LIMIT 1"
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
