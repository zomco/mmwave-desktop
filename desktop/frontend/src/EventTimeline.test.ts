import { describe, expect, it } from "vitest";
import { selectionFromPixels, zoomTimelineViewport } from "./EventTimeline";

describe("event timeline navigation", () => {
  it("zooms around the cursor and remains inside the primary search window", () => {
    const base = { start: 0, end: 3_600_000 };
    expect(zoomTimelineViewport(base, base, 0.75, -1)).toEqual({ start: 810_000, end: 3_330_000 });
    expect(zoomTimelineViewport({ start: 0, end: 60_000 }, base, 0, -1)).toEqual({ start: 0, end: 60_000 });
  });

  it("maps a dragged pixel range back to exact timeline milliseconds", () => {
    expect(selectionFromPixels(75, 25, 100, { start: 1_000, end: 5_000 })).toEqual({ start: 2_000, end: 4_000 });
    expect(selectionFromPixels(10, 11, 100, { start: 0, end: 100 })).toBeNull();
  });
});
