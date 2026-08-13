import type { Bookmark } from "./types";

export type NvrConnectionForm = {
  name: string;
  host: string;
  username: string;
  password: string;
  http_port: number;
  use_https: boolean;
  verify_tls: boolean;
};

export function nvrProbePayload(form: NvrConnectionForm) {
  return {
    host: form.host,
    username: form.username,
    password: form.password,
    http_port: form.http_port,
    use_https: form.use_https,
    verify_tls: form.verify_tls,
  };
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function formatDuration(start: string, end: string): string {
  const seconds = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export function sourcePresentation(bookmark: Bookmark): { label: string; tone: string; explanation: string } {
  if (bookmark.quality.gate === "pass" && bookmark.source.kind !== "nvr") {
    return { label: "高置信时间轴", tone: "positive", explanation: "来源质量门已通过" };
  }
  if (bookmark.quality.gate === "fail") {
    return { label: "质量未通过", tone: "danger", explanation: "仅供诊断，不进入默认高置信视图" };
  }
  if (bookmark.source.kind === "nvr") {
    return { label: "NVR 候选", tone: "neutral", explanation: "可能包含灯光、反射等误报" };
  }
  return { label: "置信度未知", tone: "warning", explanation: "来源质量尚未得到确认" };
}

export function comparisonMetrics(bookmarks: Bookmark[], labelledRecall?: number) {
  const highConfidence = bookmarks.filter(
    (item) => item.quality.gate === "pass" && item.source.kind !== "nvr",
  ).length;
  const nvrCandidates = bookmarks.filter((item) => item.source.kind === "nvr").length;
  return {
    highConfidence,
    nvrCandidates,
    reviewReduction: nvrCandidates > 0 ? 1 - highConfidence / nvrCandidates : null,
    recall: labelledRecall ?? null,
    canClaimImprovement: labelledRecall !== undefined && nvrCandidates > 0,
  };
}

export function localInputToRfc3339(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) throw new Error("请选择有效时间");
  return parsed.toISOString();
}

export function dateToLocalInput(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return (
    `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
    + `T${pad(value.getHours())}:${pad(value.getMinutes())}`
  );
}

export type TimeWindow = { from: Date; to: Date };

export const eventDefinitions = [
  { id: "motion", label: "移动侦测", category: "ordinary" },
  { id: "video_tamper", label: "遮挡报警", category: "ordinary" },
  { id: "line_crossing", label: "越界侦测", category: "smart" },
  { id: "region_intrusion", label: "区域入侵", category: "smart" },
] as const;

export type EventType = typeof eventDefinitions[number]["id"];
export type EventCategory = typeof eventDefinitions[number]["category"];

export function eventCategory(value: string): EventCategory | null {
  const normalized = value.replace(/^nvr\./, "");
  return eventDefinitions.find((item) => item.id === normalized)?.category ?? null;
}

export function lastNightWindow(
  now: Date,
  nightStartHour = 18,
  nightEndHour = 6,
): TimeWindow {
  const from = new Date(now);
  const to = new Date(now);
  const beforeNightEnd = now.getHours() < nightEndHour;
  from.setHours(nightStartHour, 0, 0, 0);
  to.setHours(nightEndHour, 0, 0, 0);
  if (beforeNightEnd) {
    from.setDate(from.getDate() - 1);
    if (to.getTime() > now.getTime()) to.setTime(now.getTime());
  } else {
    from.setDate(from.getDate() - 1);
  }
  return { from, to };
}

export function shiftWindow(window: TimeWindow, days: number): TimeWindow {
  const from = new Date(window.from);
  const to = new Date(window.to);
  from.setDate(from.getDate() + days);
  to.setDate(to.getDate() + days);
  return { from, to };
}

export function timeWindowLabel(window: TimeWindow): string {
  const formatter = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" });
  return `${formatter.format(window.from)} 晚间`;
}

const eventLabels: Record<string, string> = {
  motion: "移动侦测",
  "nvr.motion": "移动侦测",
  video_tamper: "遮挡报警",
  "nvr.video_tamper": "遮挡报警",
  line_crossing: "越界侦测",
  "nvr.line_crossing": "越界侦测",
  region_intrusion: "区域入侵",
  "nvr.region_intrusion": "区域入侵",
};

export function eventPresentation(value?: string | null): string {
  if (!value) return "录像候选";
  const normalized = value.toLowerCase();
  if (eventLabels[normalized]) return eventLabels[normalized];
  if (normalized.includes("motion") || normalized.includes("vmd")) return "移动侦测";
  if (normalized.includes("tamper") || normalized.includes("shelter") || normalized.includes("hide")) return "遮挡报警";
  if (normalized.includes("line") && normalized.includes("detect")) return "越界侦测";
  if (normalized.includes("intrusion") || normalized.includes("fielddetect")) return "区域入侵";
  return "未识别的 NVR 事件";
}
