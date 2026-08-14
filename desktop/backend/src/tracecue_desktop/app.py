"""FastAPI application implementing the TraceCue HTTP API v1 contract."""

from __future__ import annotations

import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from tracecue_engine import MAX_TIMELINE_BYTES

from . import __version__
from .config import AppConfig
from .errors import AppError
from .schemas import (
    BindingRequest,
    ChannelPatchRequest,
    ClipRequest,
    CommitImportRequest,
    DiscoveryRequest,
    NvrCreateRequest,
    NvrPatchRequest,
    ProbeRequest,
    SearchRequest,
    SearchPresetRequest,
    SettingsPatchRequest,
    TraceIterationRequest,
    TraceReviewRequest,
    TraceSessionRequest,
)
from .services import DesktopServices


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
MAX_RANGE_BYTES = 64 * 1024 * 1024


def create_app(
    config: AppConfig | None = None,
    *,
    services: DesktopServices | None = None,
    start_worker: bool = True,
) -> FastAPI:
    runtime_config = config or AppConfig.default()
    application_services = services or DesktopServices(runtime_config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_worker:
            application_services.worker.start()
        try:
            yield
        finally:
            if start_worker:
                application_services.worker.stop()
            application_services.stop_network_shares()

    app = FastAPI(
        title="TraceCue Desktop API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.services = application_services
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def request_safety(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex[:20]
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return _error_response(
                    request,
                    AppError("REQUEST_ORIGIN_REJECTED", "Cross-origin browser requests are not allowed.", 403),
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; media-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return _error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = {
            "issues": [
                {"path": ".".join(str(item) for item in error["loc"]), "message": error["msg"]}
                for error in exc.errors()
            ]
        }
        return _error_response(
            request,
            AppError("REQUEST_VALIDATION_FAILED", "Request fields did not pass validation.", 422, details),
        )

    api = "/api/v1"

    @app.get(api + "/status")
    def status() -> dict:
        return {
            "application_version": __version__,
            "schema_version": application_services.database.schema_version(),
            "ffmpeg": application_services.media_runner.availability(),
            "migration_state": "ready",
            "recovery_state": "ready",
            "bind_host": runtime_config.host,
        }

    @app.get(api + "/settings")
    def get_settings() -> dict:
        return application_services.database.settings()

    @app.patch(api + "/settings")
    def patch_settings(request: SettingsPatchRequest) -> dict:
        values = request.model_dump(exclude_none=True)
        return application_services.database.patch_settings(values)

    @app.get(api + "/diagnostics")
    def diagnostics() -> dict:
        return application_services.diagnostics()

    @app.get(api + "/diagnostics/export")
    def export_diagnostics() -> Response:
        content = json.dumps(
            application_services.diagnostics(), ensure_ascii=False, indent=2
        ).encode("utf-8")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="tracecue-diagnostics.json"'},
        )

    @app.post(api + "/nvrs/probe")
    def probe_nvr(request: ProbeRequest) -> dict:
        return application_services.probe_nvr(request.model_dump())

    @app.post(api + "/nvrs/discover")
    def discover_nvrs(request: DiscoveryRequest | None = None) -> list[dict]:
        return application_services.discover_nvrs(
            request.timeout_seconds if request else 2.5
        )

    @app.post(api + "/nvrs", status_code=201)
    def create_nvr(request: NvrCreateRequest) -> dict:
        return application_services.create_nvr(request.model_dump())

    @app.get(api + "/nvrs")
    def list_nvrs() -> list[dict]:
        return application_services.list_nvrs()

    @app.get(api + "/nvrs/{nvr_id}")
    def get_nvr(nvr_id: str) -> dict:
        return application_services.get_nvr(nvr_id)

    @app.get(api + "/nvrs/{nvr_id}/details")
    def get_nvr_details(nvr_id: str) -> dict:
        return application_services.nvr_details(nvr_id)

    @app.patch(api + "/nvrs/{nvr_id}")
    def patch_nvr(nvr_id: str, request: NvrPatchRequest) -> dict:
        return application_services.patch_nvr(nvr_id, request.model_dump(exclude_none=True))

    @app.delete(api + "/nvrs/{nvr_id}", status_code=204)
    def delete_nvr(nvr_id: str) -> Response:
        application_services.delete_nvr(nvr_id)
        return Response(status_code=204)

    @app.post(api + "/nvrs/{nvr_id}/sync-channels")
    def sync_channels(nvr_id: str) -> list[dict]:
        return application_services.sync_channels(nvr_id)

    @app.get(api + "/nvrs/{nvr_id}/channels")
    def list_channels(nvr_id: str) -> list[dict]:
        return application_services.list_channels(nvr_id)

    @app.get(api + "/nvrs/{nvr_id}/capabilities")
    def list_capabilities(nvr_id: str) -> list[dict]:
        return application_services.capabilities(nvr_id)

    @app.get(api + "/nvrs/{nvr_id}/event-audit")
    def get_event_audit(nvr_id: str) -> dict:
        return application_services.get_event_audit(nvr_id)

    @app.post(api + "/nvrs/{nvr_id}/event-audit")
    def refresh_event_audit(nvr_id: str) -> dict:
        return application_services.audit_nvr_events(nvr_id)

    @app.patch(api + "/channels/{channel_id}")
    def patch_channel(channel_id: str, request: ChannelPatchRequest) -> dict:
        return application_services.patch_channel(channel_id, request.model_dump())

    @app.get(api + "/channels/{channel_id}/snapshot")
    def get_channel_snapshot(channel_id: str) -> dict:
        return application_services.get_channel_snapshot(channel_id)

    @app.post(api + "/channels/{channel_id}/snapshot", status_code=202)
    def create_channel_snapshot(channel_id: str) -> dict:
        return application_services.enqueue_channel_snapshot(channel_id)

    @app.get(api + "/channels/{channel_id}/snapshot/content")
    def channel_snapshot_content(channel_id: str) -> FileResponse:
        return FileResponse(application_services.channel_snapshot_file(channel_id), media_type="image/jpeg")

    @app.post(api + "/search-jobs", status_code=202)
    def create_search(request: SearchRequest) -> dict:
        values = request.model_dump(by_alias=True)
        return application_services.enqueue_search(values)

    @app.get(api + "/search-jobs/{job_id}")
    def get_search(job_id: str) -> dict:
        job = application_services.get_job(job_id)
        if job["kind"] != "recording_search":
            raise AppError("JOB_KIND_MISMATCH", "Job is not a recording search.", 404)
        return job

    @app.get(api + "/search-jobs/{job_id}/results")
    def get_search_results(
        job_id: str,
        limit: int = Query(default=12, ge=1, le=200),
        offset: int = Query(default=0, ge=0, le=100_000),
    ) -> dict:
        return application_services.search_results(job_id, limit=limit, offset=offset)

    @app.get(api + "/search-presets")
    def list_search_presets() -> list[dict]:
        return application_services.list_search_presets()

    @app.post(api + "/search-presets", status_code=201)
    def create_search_preset(request: SearchPresetRequest) -> dict:
        return application_services.create_search_preset(request.model_dump())

    @app.delete(api + "/search-presets/{preset_id}", status_code=204)
    def delete_search_preset(preset_id: str) -> Response:
        application_services.delete_search_preset(preset_id)
        return Response(status_code=204)

    @app.get(api + "/trace-sessions")
    def list_trace_sessions(limit: int = Query(default=10, ge=1, le=50)) -> list[dict]:
        return application_services.list_trace_sessions(limit=limit)

    @app.post(api + "/trace-sessions", status_code=201)
    def create_trace_session(request: TraceSessionRequest) -> dict:
        return application_services.create_trace_session(request.model_dump())

    @app.get(api + "/trace-sessions/{session_id}")
    def get_trace_session(session_id: str) -> dict:
        return application_services.get_trace_session(session_id)

    @app.delete(api + "/trace-sessions/{session_id}", status_code=204)
    def delete_trace_session(session_id: str) -> Response:
        application_services.delete_trace_session(session_id)
        return Response(status_code=204)

    @app.post(api + "/trace-sessions/{session_id}/iterations", status_code=202)
    def create_trace_iteration(session_id: str, request: TraceIterationRequest) -> dict:
        return application_services.create_trace_iteration(
            session_id, request.model_dump(by_alias=True)
        )

    @app.get(api + "/trace-sessions/{session_id}/results")
    def get_trace_session_results(
        session_id: str,
        limit: int = Query(default=12, ge=1, le=200),
        offset: int = Query(default=0, ge=0, le=100_000),
        review_state: str = Query(
            default="active", pattern="^(active|all|unreviewed|reviewed|excluded|candidate)$"
        ),
        from_at: str | None = Query(default=None, alias="from"),
        to_at: str | None = Query(default=None, alias="to"),
        duration_class: str | None = Query(
            default=None, pattern="^(unknown|under_5s|5_to_30s|over_30s)$"
        ),
        summary_only: bool = Query(default=False),
    ) -> dict:
        return application_services.trace_session_results(
            session_id,
            limit=limit,
            offset=offset,
            review_state=review_state,
            from_at=from_at,
            to_at=to_at,
            duration_class=duration_class,
            summary_only=summary_only,
        )

    @app.patch(api + "/trace-sessions/{session_id}/events/{bookmark_id}")
    def patch_trace_review(
        session_id: str, bookmark_id: str, request: TraceReviewRequest
    ) -> dict:
        return application_services.patch_trace_review(session_id, bookmark_id, request.state)

    @app.get(api + "/bookmarks")
    def list_bookmarks(
        limit: int = Query(default=50),
        cursor: str | None = Query(default=None),
        high_confidence: bool | None = Query(default=None),
    ) -> dict:
        return application_services.list_bookmarks(
            limit=limit, cursor=cursor, high_confidence=high_confidence
        )

    @app.get(api + "/bookmarks/{bookmark_id}")
    def get_bookmark(bookmark_id: str) -> dict:
        return application_services.get_bookmark(bookmark_id)

    @app.get(api + "/bookmarks/{bookmark_id}/preview")
    def get_event_preview(bookmark_id: str) -> dict:
        return application_services.get_event_preview(bookmark_id)

    @app.post(api + "/bookmarks/{bookmark_id}/preview", status_code=202)
    def create_event_preview(bookmark_id: str) -> dict:
        return application_services.enqueue_event_preview(bookmark_id)

    @app.get(api + "/bookmarks/{bookmark_id}/preview/content")
    def event_preview_content(bookmark_id: str) -> FileResponse:
        return FileResponse(application_services.event_preview_file(bookmark_id), media_type="image/jpeg")

    @app.get(api + "/bookmarks/{bookmark_id}/animation")
    def get_event_animation(bookmark_id: str) -> dict:
        return application_services.get_event_animation(bookmark_id)

    @app.post(api + "/bookmarks/{bookmark_id}/animation", status_code=202)
    def create_event_animation(bookmark_id: str) -> dict:
        return application_services.enqueue_event_animation(bookmark_id)

    @app.get(api + "/bookmarks/{bookmark_id}/animation/content")
    def event_animation_content(bookmark_id: str) -> FileResponse:
        return FileResponse(application_services.event_animation_file(bookmark_id), media_type="image/webp")

    @app.post(api + "/clips", status_code=202)
    def create_clip(request: ClipRequest) -> dict:
        return application_services.enqueue_clip(request.model_dump(by_alias=True, exclude_none=True))

    @app.get(api + "/clips")
    def list_clips() -> list[dict]:
        return application_services.list_clips()

    @app.get(api + "/clips/{clip_id}")
    def get_clip(clip_id: str) -> dict:
        return application_services.get_clip(clip_id)

    @app.get(api + "/clips/{clip_id}/content")
    def clip_content(clip_id: str, range_header: str | None = Header(default=None, alias="Range")):
        path, size = application_services.clip_file(clip_id)
        if not range_header:
            return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})
        parsed = _parse_range(range_header, size)
        if parsed is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        start, end = parsed
        length = end - start + 1
        return StreamingResponse(
            _file_range(path, start, length),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(length),
            },
        )

    @app.post(api + "/clips/{clip_id}/share", status_code=201)
    def create_clip_share(clip_id: str) -> dict:
        return application_services.create_clip_share(clip_id)

    @app.delete(api + "/clips/{clip_id}", status_code=204)
    def delete_clip(clip_id: str) -> Response:
        application_services.delete_clip(clip_id)
        return Response(status_code=204)

    @app.get(api + "/jobs")
    def list_jobs() -> list[dict]:
        return application_services.list_jobs()

    @app.get(api + "/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return application_services.get_job(job_id)

    @app.post(api + "/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        return application_services.cancel_job(job_id)

    @app.post(api + "/timeline-imports/inspect", status_code=201)
    async def inspect_import(request: Request) -> dict:
        declared = request.headers.get("content-length")
        if declared and int(declared) > MAX_TIMELINE_BYTES:
            raise AppError("TIMELINE_TOO_LARGE", "Timeline document exceeds the upload limit.", 413)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_TIMELINE_BYTES:
                raise AppError("TIMELINE_TOO_LARGE", "Timeline document exceeds the upload limit.", 413)
        return application_services.inspect_import(bytes(content))

    @app.get(api + "/timeline-imports/{import_id}")
    def get_import(import_id: str) -> dict:
        return application_services.get_import(import_id)

    @app.post(api + "/timeline-imports/{import_id}/commit")
    def commit_import(import_id: str, request: CommitImportRequest | None = None) -> dict:
        return application_services.commit_import(import_id, request.content_hash if request else None)

    @app.get(api + "/sources")
    def list_sources() -> list[dict]:
        return application_services.list_sources()

    @app.get(api + "/source-channels")
    def list_source_channels() -> list[dict]:
        return application_services.list_source_channels()

    @app.put(api + "/source-channels/{source_channel_id}/binding")
    def bind_source_channel(source_channel_id: str, request: BindingRequest) -> dict:
        return application_services.bind_source_channel(
            source_channel_id, request.model_dump(exclude_none=True)
        )

    _mount_frontend(app, runtime_config.frontend_dir)
    return app


def _error_response(request: Request, error: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": request_id,
                "details": error.details,
            }
        },
        headers={"X-Request-ID": request_id},
    )


def _parse_range(value: str, size: int) -> tuple[int, int] | None:
    match = _RANGE.fullmatch(value.strip())
    if not match or "," in value:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if first:
        start = int(first)
        end = int(last) if last else min(size - 1, start + MAX_RANGE_BYTES - 1)
    else:
        suffix = min(int(last), MAX_RANGE_BYTES)
        if suffix <= 0:
            return None
        start = max(0, size - suffix)
        end = size - 1
    if start >= size or end < start or end >= size or end - start + 1 > MAX_RANGE_BYTES:
        return None
    return start, end


def _file_range(path: Path, start: int, length: int) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _mount_frontend(app: FastAPI, frontend_dir: Path | None) -> None:
    if not frontend_dir or not (frontend_dir / "index.html").exists():
        @app.get("/", include_in_schema=False)
        def backend_only() -> dict[str, str]:
            return {"application": "TraceCue Desktop", "status": "frontend_not_built"}
        return
    assets = frontend_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa(spa_path: str):
        requested = (frontend_dir / spa_path).resolve()
        if requested.is_file() and requested.is_relative_to(frontend_dir.resolve()):
            return FileResponse(requested)
        return FileResponse(frontend_dir / "index.html")
