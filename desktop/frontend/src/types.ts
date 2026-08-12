export interface Nvr {
  id: string;
  name: string;
  host: string;
  http_port: number;
  use_https: boolean;
  verify_tls: boolean;
  model: string | null;
  firmware: string | null;
  timezone: string | null;
  clock_skew_ms: number | null;
}

export interface DiscoveredDevice {
  host: string;
  http_port: number;
  use_https: boolean;
  name: string;
  model: string | null;
  device_types: string[];
  discovery_protocol: "onvif_ws_discovery" | "isapi_private_subnet_probe";
  already_added: boolean;
}

export interface Channel {
  id: string;
  nvr_id: string;
  external_channel_id: string;
  primary_track_id: string | null;
  stream_track_ids: string[];
  device_name: string;
  alias: string | null;
  online: boolean;
}

export interface Job {
  id: string;
  kind: string;
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "interrupted";
  progress: number;
  error: { code: string; message: string; details: Record<string, unknown> } | null;
  result: Record<string, unknown> | null;
}

export interface Bookmark {
  id: string;
  source: { id: string; kind: string; external_id: string };
  source_channel: { id: string; label: string; kind: string };
  media_channel_id: string | null;
  media_channel_label: string | null;
  event_type: string;
  raw_start_at: string;
  raw_end_at: string;
  clock_correction_ms: number;
  start_at: string;
  end_at: string;
  quality: { gate: "pass" | "fail" | "unknown"; score: number | null };
  confidence: number | null;
  media_window: { start_at: string; end_at: string } | null;
  tags: string[];
  attributes: {
    hikvision?: {
      classification?: string;
      canonical_event_type?: string;
      area_name?: string | null;
      search_job_id?: string;
    };
    [key: string]: unknown;
  };
}

export interface SearchResults {
  job_id: string;
  state: Job["state"];
  items: Bookmark[];
}

export interface SearchPreset {
  id: string;
  name: string;
  nvr_id: string;
  area_name: string;
  channel_ids: string[];
  event_types: string[];
  created_at: string;
  updated_at: string;
  last_used_at: string;
}

export interface EventPreview {
  bookmark_id: string;
  job_id: string;
  status: "queued" | "generating" | "ready" | "failed";
  content_url: string | null;
}

export interface EventRule {
  channel_external_id: string;
  channel_label: string;
  track_id: string | null;
  event_type: string;
  state: "supported" | "unsupported" | "degraded" | "unknown";
  enabled: boolean | null;
  notification_configured: boolean | null;
  sensitivity: number | null;
  region_count: number | null;
  schedule_block_count: number | null;
  note: string | null;
}

export interface EventAudit {
  observed_at: string;
  rules: EventRule[];
  warnings: { code: string; message: string }[];
}

export interface ClipOrigin {
  bookmark_id: string;
  search_job_id: string | null;
  area_name: string | null;
  channel_label: string | null;
  event_type: string;
  classification: string | null;
  event_window: { start_at: string; end_at: string };
  candidate_window_capped: boolean;
}

export interface Clip {
  id: string;
  job_id: string;
  channel_id: string;
  requested_window: { start_at: string; end_at: string };
  actual_window: { start_at: string; end_at: string } | null;
  status: "queued" | "generating" | "ready" | "failed";
  video_codec: string | null;
  audio_codec: string | null;
  size_bytes: number | null;
  created_at: string;
  content_url: string | null;
  origin: ClipOrigin | null;
}
