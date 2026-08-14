import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import type { TraceTimelineEvent } from "./types";
import { Button } from "./ui";

export type TimelineWindow = { start_at: string; end_at: string };
type NumericWindow = { start: number; end: number };

export function zoomTimelineViewport(
  viewport: NumericWindow,
  base: NumericWindow,
  cursorRatio: number,
  deltaY: number,
): NumericWindow {
  const baseSpan = base.end - base.start;
  const minimumSpan = Math.min(baseSpan, 60_000);
  const currentSpan = viewport.end - viewport.start;
  const nextSpan = Math.min(baseSpan, Math.max(minimumSpan, currentSpan * (deltaY > 0 ? 1.35 : 0.7)));
  const ratio = Math.min(1, Math.max(0, cursorRatio));
  const anchor = viewport.start + currentSpan * ratio;
  let start = anchor - nextSpan * ratio;
  start = Math.max(base.start, Math.min(base.end - nextSpan, start));
  return { start, end: start + nextSpan };
}

export function selectionFromPixels(
  firstPixel: number,
  lastPixel: number,
  width: number,
  viewport: NumericWindow,
): NumericWindow | null {
  if (width <= 0 || Math.abs(lastPixel - firstPixel) < 3) return null;
  const left = Math.max(0, Math.min(width, Math.min(firstPixel, lastPixel)));
  const right = Math.max(0, Math.min(width, Math.max(firstPixel, lastPixel)));
  const span = viewport.end - viewport.start;
  return {
    start: viewport.start + (left / width) * span,
    end: viewport.start + (right / width) * span,
  };
}

function timelineLabel(value: number, span: number) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: span > 86_400_000 ? "2-digit" : undefined,
    day: span > 86_400_000 ? "2-digit" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    second: span <= 10 * 60_000 ? "2-digit" : undefined,
    hour12: false,
  }).format(new Date(value));
}

export function EventTimeline({
  from,
  to,
  events,
  selected,
  onSelect,
}: {
  from: string;
  to: string;
  events: TraceTimelineEvent[];
  selected: TimelineWindow | null;
  onSelect: (window: TimelineWindow) => void;
}) {
  const base = useMemo(() => ({ start: new Date(from).getTime(), end: new Date(to).getTime() }), [from, to]);
  const [viewport, setViewport] = useState<NumericWindow>(base);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragCurrent, setDragCurrent] = useState<number | null>(null);
  const surface = useRef<HTMLDivElement>(null);

  useEffect(() => setViewport(base), [base.start, base.end]);

  const visible = useMemo(() => events.map((event, index) => ({
    event,
    index,
    start: new Date(event.start_at).getTime(),
    end: new Date(event.end_at).getTime(),
  })).filter((item) => item.start < viewport.end && item.end > viewport.start), [events, viewport]);

  const density = useMemo(() => {
    const bins = new Array(120).fill(0) as number[];
    const span = viewport.end - viewport.start;
    for (const item of visible) {
      const first = Math.max(0, Math.min(119, Math.floor(((item.start - viewport.start) / span) * 120)));
      const last = Math.max(first, Math.min(119, Math.floor(((item.end - viewport.start) / span) * 120)));
      for (let index = first; index <= last; index += 1) bins[index] = (bins[index] ?? 0) + 1;
    }
    return { bins, max: Math.max(1, ...bins) };
  }, [visible, viewport]);

  const coordinate = (event: PointerEvent<HTMLDivElement>) => {
    const rect = surface.current?.getBoundingClientRect();
    return rect ? Math.max(0, Math.min(rect.width, event.clientX - rect.left)) : 0;
  };

  function finishDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragStart === null || !surface.current) return;
    const selection = selectionFromPixels(dragStart, coordinate(event), surface.current.clientWidth, viewport);
    setDragStart(null);
    setDragCurrent(null);
    if (selection) onSelect({ start_at: new Date(selection.start).toISOString(), end_at: new Date(selection.end).toISOString() });
  }

  function wheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const rect = surface.current?.getBoundingClientRect();
    if (!rect) return;
    setViewport((current) => zoomTimelineViewport(current, base, (event.clientX - rect.left) / rect.width, event.deltaY));
  }

  const span = viewport.end - viewport.start;
  const selectedStart = selected ? new Date(selected.start_at).getTime() : null;
  const selectedEnd = selected ? new Date(selected.end_at).getTime() : null;
  const selectionLeft = selectedStart === null ? 0 : ((selectedStart - viewport.start) / span) * 100;
  const selectionWidth = selectedEnd === null || selectedStart === null ? 0 : ((selectedEnd - selectedStart) / span) * 100;
  const draftLeft = dragStart === null || dragCurrent === null || !surface.current ? 0 : Math.min(dragStart, dragCurrent) / surface.current.clientWidth * 100;
  const draftWidth = dragStart === null || dragCurrent === null || !surface.current ? 0 : Math.abs(dragCurrent - dragStart) / surface.current.clientWidth * 100;

  return <div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><strong className="text-sm">事件时间轴</strong><p className="mt-1 text-xs text-slate-500">点击事件条，或拖放绘制子时间区间；在时间轴上滚动可围绕光标缩放。</p></div>
      <Button type="button" variant="ghost" onClick={() => setViewport(base)} disabled={viewport.start === base.start && viewport.end === base.end}>复位缩放</Button>
    </div>
    <div
      ref={surface}
      className="relative mt-3 h-28 touch-none select-none overflow-hidden rounded-xl border border-slate-200 bg-slate-950"
      onWheel={wheel}
      onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); const value = coordinate(event); setDragStart(value); setDragCurrent(value); }}
      onPointerMove={(event) => { if (dragStart !== null) setDragCurrent(coordinate(event)); }}
      onPointerUp={finishDrag}
      onPointerCancel={() => { setDragStart(null); setDragCurrent(null); }}
    >
      <div className="absolute inset-x-3 top-2 bottom-7">
        {density.bins.map((count, index) => count > 0 && <span key={index} className="absolute bottom-0 top-0 bg-emerald-400" style={{ left: `${index / density.bins.length * 100}%`, width: `${100 / density.bins.length}%`, opacity: 0.04 + count / density.max * 0.12 }} />)}
        {visible.map(({ event, index, start, end }) => {
          const left = Math.max(0, (start - viewport.start) / span * 100);
          const width = Math.max(0.35, (Math.min(end, viewport.end) - Math.max(start, viewport.start)) / span * 100);
          const bin = Math.max(0, Math.min(119, Math.floor(((start - viewport.start) / span) * 120)));
          const intensity = (density.bins[bin] ?? 0) / density.max;
          return <button
            type="button"
            key={event.id}
            title={`${timelineLabel(start, span)} – ${timelineLabel(end, span)}`}
            aria-label={`选择 ${timelineLabel(start, span)} 开始的事件`}
            className="absolute h-4 rounded-sm border border-emerald-100/70 shadow-sm transition hover:z-20 hover:bg-amber-300"
            style={{ left: `${left}%`, width: `${width}%`, top: `${8 + index % 3 * 18}px`, backgroundColor: `rgba(16, 185, 129, ${0.48 + intensity * 0.48})` }}
            onPointerDown={(pointerEvent) => pointerEvent.stopPropagation()}
            onClick={() => onSelect({ start_at: event.start_at, end_at: event.end_at })}
          />;
        })}
        {selected && selectionLeft < 100 && selectionLeft + selectionWidth > 0 && <span className="pointer-events-none absolute inset-y-0 border-2 border-amber-300 bg-amber-300/15" style={{ left: `${selectionLeft}%`, width: `${selectionWidth}%` }} />}
        {dragStart !== null && <span className="pointer-events-none absolute inset-y-0 border-2 border-sky-300 bg-sky-300/20" style={{ left: `${draftLeft}%`, width: `${draftWidth}%` }} />}
      </div>
      <div className="absolute inset-x-3 bottom-2 flex justify-between font-mono text-[10px] text-slate-300">{Array.from({ length: 5 }, (_, index) => <span key={index}>{timelineLabel(viewport.start + span * index / 4, span)}</span>)}</div>
    </div>
    <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-slate-500"><span>当前尺度：{timelineLabel(viewport.start, span)} – {timelineLabel(viewport.end, span)}</span><span>{visible.length} 个可见事件</span></div>
  </div>;
}
