import { useLoad } from "../hooks";
import { api } from "../api";
import { Empty, Header, Problem, Spinner, card } from "../ui";

type FusionEvent = {
  event_id: string;
  event_type: string;
  zone_id: string;
  timestamp: number;
  snapshot_path?: string;
};

type FusionList = { available: boolean; events: FusionEvent[] };

export function RadarPage() {
  const events = useLoad(() => api<FusionList>("/fusion-events"));
  if (events.loading) return <Spinner />;
  return <>
    <Header eyebrow="RADAR REVIEW" title="雷达回查" description="主路径是常驻服务保存的区域事件和直播抓拍。NVR 时间轴是冷存档，可能很慢，不在这里打开。" />
    <Problem error={events.error} />
    {!events.data?.available && <Empty title="常驻回查未启动" description="界面可以关掉。历史在 127.0.0.1 的常驻服务里，不在 NVR 上。" />}
    {events.data?.available && events.data.events.length === 0 && <Empty title="还没有雷达事件" description="有人进入、停留或穿过区域后，事件会出现在这里。" />}
    <div className="grid gap-3">
      {events.data?.events.map((item) => <article key={item.event_id} className={`${card} px-4 py-3`}>
        <strong>{item.zone_id}</strong>
        <span className="ml-3 font-mono text-xs text-slate-500">{item.event_type}</span>
        {item.snapshot_path && <p className="mt-1 font-mono text-xs text-slate-500">{item.snapshot_path}</p>}
      </article>)}
    </div>
  </>;
}
