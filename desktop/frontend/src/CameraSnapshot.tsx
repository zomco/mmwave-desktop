import { useCallback, useEffect, useRef, useState } from "react";
import { api, post } from "./api";
import type { Channel, ChannelSnapshot, RuleOverlay } from "./types";
import { Spinner } from "./ui";

export function CameraSnapshot({ channel, overlays = [], priority = false }: { channel: Channel; overlays?: RuleOverlay[]; priority?: boolean }) {
  const [snapshot, setSnapshot] = useState<ChannelSnapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(priority);
  const mounted = useRef(true);
  const container = useRef<HTMLDivElement>(null);
  const load = useCallback(async () => {
    try {
      let current = await post<ChannelSnapshot>(`/channels/${channel.id}/snapshot`);
      if (mounted.current) setSnapshot(current);
      for (let attempt = 0; attempt < 80 && (["queued", "generating"].includes(current.status) || current.refreshing); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        current = await api<ChannelSnapshot>(`/channels/${channel.id}/snapshot`);
        if (mounted.current) setSnapshot(current);
      }
      if (mounted.current) setFailed(current.status === "failed");
    } catch { if (mounted.current) setFailed(true); }
  }, [channel.id]);

  useEffect(() => {
    mounted.current = true;
    if (visible) void load();
    return () => { mounted.current = false; };
  }, [visible, load]);

  useEffect(() => {
    if (priority) {
      setVisible(true);
      return;
    }
    if (visible) return;
    const element = container.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "320px 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [priority, visible]);

  return <div ref={container} className="relative aspect-video overflow-hidden rounded-xl bg-[#142e29]">
    {snapshot?.status === "ready" && snapshot.content_url
      ? <img className="h-full w-full object-cover" src={`${snapshot.content_url}?v=${encodeURIComponent(snapshot.captured_at ?? snapshot.job_id)}`} alt={`${channel.alias || "未命名摄像机"}画面`} />
      : <div className="grid h-full place-items-center text-emerald-100/70">{failed ? <span className="text-xs">摄像机画面暂不可用</span> : visible ? <Spinner label="读取摄像机画面" /> : <span className="text-xs">滚动到这里时读取画面</span>}</div>}
    {snapshot?.status === "ready" && snapshot.refreshing && <span className="absolute right-2 top-2 rounded-md bg-black/65 px-2 py-1 text-[10px] text-white">后台刷新中</span>}
    <RuleOverlaySvg overlays={overlays} />
  </div>;
}

function RuleOverlaySvg({ overlays }: { overlays: RuleOverlay[] }) {
  if (!overlays.length) return null;
  const colors = ["#6ee7b7", "#fbbf24", "#60a5fa", "#f472b6"];
  return <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="NVR 事件规则区域">
    {overlays.map((overlay, index) => overlay.kind === "grid"
      ? overlay.active_cells.map(([x, y]) => <rect key={`${index}-${x}-${y}`} x={x * 1000 / overlay.width} y={y * 1000 / overlay.height} width={1000 / overlay.width} height={1000 / overlay.height} fill="rgba(16,185,129,.22)" stroke="rgba(110,231,183,.38)" strokeWidth="1" />)
      : overlay.kind === "line"
        ? <g key={index}><polyline points={overlay.points.map(([x, y]) => `${x * 1000 / overlay.width},${y * 1000 / overlay.height}`).join(" ")} fill="none" stroke={colors[index % colors.length]} strokeWidth="8" vectorEffect="non-scaling-stroke" /><text x={(overlay.points[0]?.[0] ?? 0) * 1000 / overlay.width} y={(overlay.points[0]?.[1] ?? 0) * 1000 / overlay.height - 20} fill="white" stroke="rgba(0,0,0,.8)" strokeWidth="5" paintOrder="stroke" fontSize="42" fontWeight="700">警戒线 {index + 1}</text></g>
        : <g key={index}><polygon points={overlay.points.map(([x, y]) => `${x * 1000 / overlay.width},${y * 1000 / overlay.height}`).join(" ")} fill={`${colors[index % colors.length]}33`} stroke={colors[index % colors.length]} strokeWidth="6" vectorEffect="non-scaling-stroke" /><text x={(overlay.points[0]?.[0] ?? 0) * 1000 / overlay.width} y={(overlay.points[0]?.[1] ?? 0) * 1000 / overlay.height - 20} fill="white" stroke="rgba(0,0,0,.8)" strokeWidth="5" paintOrder="stroke" fontSize="42" fontWeight="700">区域 {index + 1}</text></g>)}
  </svg>;
}
