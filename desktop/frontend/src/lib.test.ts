import { describe, expect, it } from "vitest";
import { comparisonMetrics, dateToLocalInput, eventCategory, eventPresentation, lastNightWindow, nvrProbePayload, shiftWindow, sourcePresentation } from "./lib";
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
    attributes: {},
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

describe("NVR onboarding payloads", () => {
  it("does not send the display name to the strict read-only probe contract", () => {
    const payload = nvrProbePayload({
      name: "Front desk",
      host: "192.0.2.10",
      username: "operator",
      password: "fixture-password",
      http_port: 80,
      use_https: false,
      verify_tls: true,
    });

    expect(payload).toEqual({
      host: "192.0.2.10",
      username: "operator",
      password: "fixture-password",
      http_port: 80,
      use_https: false,
      verify_tls: true,
    });
    expect(payload).not.toHaveProperty("name");
  });
});

describe("local search windows", () => {
  it("formats datetime-local defaults with local clock fields instead of UTC fields", () => {
    const localTime = new Date(2026, 7, 12, 18, 30, 45);
    expect(dateToLocalInput(localTime)).toBe("2026-08-12T18:30");
  });

  it("builds the most recent completed night with local calendar fields", () => {
    const window = lastNightWindow(new Date(2026, 7, 13, 10, 30), 18, 6);
    expect(dateToLocalInput(window.from)).toBe("2026-08-12T18:00");
    expect(dateToLocalInput(window.to)).toBe("2026-08-13T06:00");
  });

  it("keeps early-morning searches inside the current overnight window", () => {
    const now = new Date(2026, 7, 13, 2, 30);
    const window = lastNightWindow(now, 18, 6);
    expect(dateToLocalInput(window.from)).toBe("2026-08-12T18:00");
    expect(dateToLocalInput(window.to)).toBe("2026-08-13T02:30");
  });

  it("shifts overnight windows by local calendar days", () => {
    const shifted = shiftWindow({ from: new Date(2026, 7, 12, 18), to: new Date(2026, 7, 13, 6) }, -1);
    expect(dateToLocalInput(shifted.from)).toBe("2026-08-11T18:00");
    expect(dateToLocalInput(shifted.to)).toBe("2026-08-12T06:00");
  });
});

describe("event presentation", () => {
  it("maps vendor classifications to user-facing behavior names", () => {
    expect(eventPresentation("nvr.video_tamper")).toBe("遮挡报警");
    expect(eventPresentation("nvr.region_intrusion")).toBe("区域入侵");
    expect(eventCategory("line_crossing")).toBe("smart");
    expect(eventCategory("motion")).toBe("ordinary");
  });
});
