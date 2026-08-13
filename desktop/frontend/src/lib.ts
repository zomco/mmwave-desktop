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

const eventLabels: Record<string, string> = {
  motion: "移动侦测",
  "nvr.motion": "移动侦测",
  line_crossing: "越界侦测",
  "nvr.line_crossing": "越界侦测",
  region_intrusion: "区域入侵",
  "nvr.region_intrusion": "区域入侵",
  smart: "智能事件",
  "nvr.smart": "智能事件",
  continuous: "连续录像",
  "nvr.continuous": "连续录像",
};

export function eventPresentation(value?: string | null): string {
  if (!value) return "录像候选";
  const normalized = value.toLowerCase();
  if (eventLabels[normalized]) return eventLabels[normalized];
  if (normalized.includes("timing") || normalized.includes("continuous")) return "连续录像";
  if (normalized.includes("motion") || normalized.includes("vmd")) return "移动侦测";
  if (normalized.includes("line") && normalized.includes("detect")) return "越界侦测";
  if (normalized.includes("intrusion") || normalized.includes("fielddetect")) return "区域入侵";
  return "其他 NVR 事件";
}
