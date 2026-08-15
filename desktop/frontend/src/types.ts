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
  utc_offset_minutes: number | null;
}

export interface NvrDeviceDetails {
  device_name: string | null;
  device_type: string | null;
  model: string | null;
  firmware: string | null;
  serial_number: string | null;
  mac_address: string | null;
  device_id: string | null;
  firmware_released_date: string | null;
  encoder_version: string | null;
  encoder_released_date: string | null;
}

export interface CameraDeviceDetails {
  external_channel_id: string;
  channel_id: string;
  label: string;
  name: string | null;
  online: boolean | null;
  model: string | null;
  firmware: string | null;
  serial_number: string | null;
  device_id: string | null;
  protocol: string | null;
  address: string | null;
  manage_port: number | null;
  source_input_port: number | null;
  stream_type: string | null;
}

export interface DeviceDetails {
  observed_at: string;
  nvr: NvrDeviceDetails;
  cameras: CameraDeviceDetails[];
  connection: {
    host: string;
    http_port: number;
    use_https: boolean;
    timezone: string | null;
    clock_skew_ms: number | null;
  };
  warnings: { code: string; message: string }[];
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

export interface VisualAnalysisAvailability {
  available: boolean;
  code: string | null;
  message: string;
  model_id: string | null;
  supported_event_types: string[];
  target_classes: string[];
}

export interface AppStatus {
  application_version: string;
  schema_version: number;
  visual_analysis: VisualAnalysisAvailability;
}

export type VisualVerdict =
  | "confirmed_trigger"
  | "target_present_no_trigger"
  | "no_supported_target_detected"
  | "uncertain";

export interface EventVisualAnalysis {
  bookmark_id: string;
  job_id: string;
  status: "queued" | "analyzing" | "ready" | "failed";
  progress: number;
  verdict: VisualVerdict | null;
  result: {
    reason_code: string;
    confidence: number | null;
    trigger_at: string | null;
    target_classes: string[];
    track_count: number;
    frame_count: number;
    detection_count: number;
    model_id: string;
    analyzed_window: { start_at: string; end_at: string };
    evidence_animation_ready: boolean;
  } | null;
  evidence_content_url: string | null;
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
      event_duration_ms?: number | null;
      duration_source?: "paired_alarm_log" | "unknown";
    };
    [key: string]: unknown;
  };
  review_state?: ReviewState;
  search_job_id?: string;
  visual_analysis?: EventVisualAnalysis | null;
}

export type ReviewState = "unreviewed" | "reviewed" | "excluded" | "candidate";
export type ReviewFilter = ReviewState | "active" | "all";

export interface TraceIteration {
  id: string;
  label: string;
  from: string;
  to: string;
  state: "running" | "succeeded" | "failed" | "partial";
  result_count: number;
  jobs: Job[];
  created_at: string;
}

export interface TraceSession {
  id: string;
  channel_ids: string[];
  event_types: string[];
  preset_id: string | null;
  iterations: TraceIteration[];
  result_count: number;
  created_at: string;
  updated_at: string;
}

export interface TraceTimelineEvent {
  id: string;
  start_at: string;
  end_at: string;
  duration_ms: number | null;
  cluster_size: number;
}

export type DurationClass = "unknown" | "under_5s" | "5_to_30s" | "over_30s";
export type ActivityMode = "all" | "isolated" | "clustered";

export interface TraceSessionResults {
  session_id: string;
  items: Bookmark[];
  total: number;
  counts: Record<ReviewState, number>;
  timeline: TraceTimelineEvent[];
  timeline_truncated: boolean;
  selected_window: { start_at: string; end_at: string } | null;
  duration_buckets: Record<DurationClass, number>;
  duration_range: { known_count: number; min_ms: number | null; max_ms: number | null };
  activity_mode: ActivityMode;
  activity_counts: Record<Exclude<ActivityMode, "all">, number>;
  activity_cluster_gap_ms: number;
  limit: number;
  offset: number;
  has_more: boolean;
  summary_only: boolean;
}

export interface AppSettings {
  clip_quota_bytes: number;
  pre_roll_ms: number;
  post_roll_ms: number;
  preferred_port: number;
  night_start_hour: number;
  night_end_hour: number;
}

export interface SearchResults {
  job_id: string;
  state: Job["state"];
  items: Bookmark[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
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
  progress: number;
  content_url: string | null;
}

export interface ChannelSnapshot {
  channel_id: string;
  job_id: string;
  status: "queued" | "generating" | "ready" | "failed";
  captured_at: string | null;
  expires_at: string | null;
  stale: boolean;
  refreshing: boolean;
  source: "live_low_rate" | "recent_recording" | null;
  content_url: string | null;
}

export interface EventAnimation extends EventPreview {}

export interface RuleOverlay {
  kind: "grid" | "polygon" | "line";
  width: number;
  height: number;
  points: [number, number][];
  active_cells: [number, number][];
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
  overlays: RuleOverlay[];
}

export interface EventAudit {
  schema_version: number;
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
  padding_trimmed_for_neighbor_events: boolean;
  candidate_window_capped: boolean;
  time_basis?: "nvr_index";
}

export interface Clip {
  id: string;
  job_id: string;
  channel_id: string;
  requested_window: { start_at: string; end_at: string };
  actual_window: { start_at: string; end_at: string } | null;
  status: "queued" | "generating" | "ready" | "failed";
  progress: number;
  video_codec: string | null;
  audio_codec: string | null;
  size_bytes: number | null;
  created_at: string;
  content_url: string | null;
  origin: ClipOrigin | null;
}

export interface ClipShare {
  clip_id: string;
  url: string;
  expires_at: string;
}
