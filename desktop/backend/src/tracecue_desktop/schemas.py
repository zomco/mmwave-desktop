"""HTTP request schemas; responses remain explicit service dictionaries."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EventType = Literal["motion", "video_tamper", "line_crossing", "region_intrusion"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProbeRequest(ApiModel):
    host: str
    username: str
    password: str
    http_port: int = Field(default=80, ge=1, le=65535)
    use_https: bool = False
    verify_tls: bool = True


class NvrCreateRequest(ProbeRequest):
    name: str | None = Field(default=None, max_length=200)


class NvrPatchRequest(ApiModel):
    name: str | None = Field(default=None, max_length=200)
    host: str | None = None
    http_port: int | None = Field(default=None, ge=1, le=65535)
    use_https: bool | None = None
    verify_tls: bool | None = None
    username: str | None = None
    password: str | None = None


class ChannelPatchRequest(ApiModel):
    alias: str | None = Field(default=None, max_length=200)


class SearchRequest(ApiModel):
    nvr_id: str
    channel_ids: list[str]
    from_at: str = Field(alias="from")
    to_at: str = Field(alias="to")
    source_modes: list[Literal["historical_event_log", "record_classification"]] = Field(
        default_factory=lambda: ["historical_event_log"], max_length=1
    )
    area_name: str | None = Field(default=None, max_length=200)
    event_types: list[EventType] = Field(default_factory=list, max_length=4)
    preset_id: str | None = None


class SearchPresetRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    nvr_id: str | None = None
    area_name: str = Field(default="", max_length=200)
    channel_ids: list[str] = Field(min_length=1, max_length=64)
    event_types: list[EventType] = Field(default_factory=list, max_length=4)


class TraceSessionRequest(ApiModel):
    channel_ids: list[str] = Field(min_length=1, max_length=64)
    event_types: list[EventType] = Field(default_factory=list, max_length=4)
    preset_id: str | None = None


class TraceIterationRequest(ApiModel):
    from_at: str = Field(alias="from")
    to_at: str = Field(alias="to")
    label: str = Field(default="自定义时间", min_length=1, max_length=100)


class TraceReviewRequest(ApiModel):
    state: str = Field(pattern="^(unreviewed|reviewed|excluded|candidate)$")


class DiscoveryRequest(ApiModel):
    timeout_seconds: float = Field(default=2.5, ge=0.5, le=5.0)


class WindowOverride(ApiModel):
    pre_roll_ms: int = Field(default=5_000, ge=0, le=3_600_000)
    post_roll_ms: int = Field(default=10_000, ge=0, le=3_600_000)
    max_duration_ms: int | None = Field(default=None, ge=1_000, le=600_000)


class ClipRequest(ApiModel):
    bookmark_id: str | None = None
    channel_id: str | None = None
    from_at: str | None = Field(default=None, alias="from")
    to_at: str | None = Field(default=None, alias="to")
    window_override: WindowOverride | None = None
    audio_policy: str = Field(default="prefer", pattern="^(prefer|preserve|omit)$")
    search_job_id: str | None = None


class SettingsPatchRequest(ApiModel):
    clip_quota_bytes: int | None = Field(default=None, ge=100 * 1024 * 1024)
    pre_roll_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    post_roll_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    preferred_port: int | None = Field(default=None, ge=1024, le=65535)
    night_start_hour: int | None = Field(default=None, ge=0, le=23)
    night_end_hour: int | None = Field(default=None, ge=0, le=23)


class CommitImportRequest(ApiModel):
    content_hash: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")


class BindingRequest(ApiModel):
    space_id: str | None = None
    space_name: str | None = Field(default=None, min_length=1, max_length=200)
    nvr_channel_id: str
    clock_correction_ms: int = Field(default=0, ge=-86_400_000, le=86_400_000)
