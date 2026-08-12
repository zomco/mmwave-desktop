import type { Bookmark } from "./types";

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

