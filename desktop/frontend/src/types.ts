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
}

export interface SourceChannel {
  id: string;
  source_id: string;
  external_key: string;
  label: string;
  kind: string;
  external_source_id: string;
  source_kind: string;
  space_id: string | null;
  space_name: string | null;
  nvr_channel_id: string | null;
  clock_correction_ms: number | null;
}

