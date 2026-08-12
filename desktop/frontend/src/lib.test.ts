import { describe, expect, it } from "vitest";
import { comparisonMetrics, sourcePresentation } from "./lib";
import type { Bookmark } from "./types";

function bookmark(overrides: Partial<Bookmark>): Bookmark {
  return {
    id: "one",
    source: { id: "source", kind: "nvr", external_id: "fixture" },
    source_channel: { id: "channel", label: "Hall", kind: "nvr_event" },
    media_channel_id: "camera",
    media_channel_label: "Hall camera",
    event_type: "nvr.recording",
    raw_start_at: "2026-08-12T08:00:00Z",
    raw_end_at: "2026-08-12T08:00:10Z",
    clock_correction_ms: 0,
    start_at: "2026-08-12T08:00:00Z",
    end_at: "2026-08-12T08:00:10Z",
    quality: { gate: "unknown", score: null },
    confidence: null,
    media_window: null,
    tags: [],
    ...overrides,
  };
}

describe("honest source presentation", () => {
  it("never labels an NVR-originated candidate high confidence", () => {
    const item = bookmark({ quality: { gate: "pass", score: 1 } });
    expect(sourcePresentation(item).label).toBe("NVR 候选");
  });

  it("requires labelled recall before claiming improvement", () => {
    const items = [bookmark({ id: "nvr" }), bookmark({ id: "sensor", source: { id: "source-2", kind: "timeline", external_id: "gateway" }, quality: { gate: "pass", score: 0.9 } })];
    expect(comparisonMetrics(items).canClaimImprovement).toBe(false);
    expect(comparisonMetrics(items, 0.98).canClaimImprovement).toBe(true);
  });
});
