import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, post } from "../api";
import { useLoad } from "../hooks";
import { dateToLocalInput, formatDateTime, formatDuration, localInputToRfc3339 } from "../lib";
import type { View, NoticeSetter } from "../App";
import type { Bookmark, Channel, EventPreview, Job, Nvr, SearchPreset, SearchResults } from "../types";
import { Badge, Button, Empty, Header, Problem, Spinner, card, field } from "../ui";

const eventOptions = [
  { id: "motion", label: "移动侦测" },
  { id: "line_crossing", label: "越界侦测" },
  { id: "region_intrusion", label: "区域入侵" },
  { id: "smart", label: "其他智能事件" },
  { id: "continuous", label: "连续录像" },
];

export function TracePage({ navigate, setNotice }: { navigate: (view: View) => void; setNotice: NoticeSetter }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const presets = useLoad(() => api<SearchPreset[]>("/search-presets"));
  const [nvrId, setNvrId] = useState("");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [areaName, setAreaName] = useState("");
  const [presetId, setPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const now = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(dateToLocalInput(new Date(now.getTime() - 60 * 60 * 1000)));
  const [to, setTo] = useState(dateToLocalInput(now));
  const [job, setJob] = useState<Job | null>(null);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [previews, setPreviews] = useState<Record<string, EventPreview>>({});
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);

  useEffect(() => {
    if (!nvrId && nvrs.data?.[0]) setNvrId(nvrs.data[0].id);
  }, [nvrs.data, nvrId]);
  useEffect(() => {
    if (!nvrId) { setChannels([]); return; }
    api<Channel[]>(`/nvrs/${nvrId}/channels`).then((items) => {
      setChannels(items);
      setSelectedChannels((current) => current.filter((id) => items.some((item) => item.id === id)));
    }).catch((caught) => setError(caught as ApiError));
  }, [nvrId]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.state)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api<Job>(`/jobs/${job.id}`);
        setJob(next);
        if (next.state === "succeeded") {
          const found = await api<SearchResults>(`/search-jobs/${next.id}/results`);
          setResults(found);
          setSelectedEvents([]);
        }
      } catch (caught) { setError(caught as ApiError); }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [job]);

  function applyPreset(id: string) {
    setPresetId(id);
    const preset = presets.data?.find((item) => item.id === id);
    if (!preset) return;
    setNvrId(preset.nvr_id);
    setAreaName(preset.area_name);
    setSelectedChannels(preset.channel_ids);
    setEventTypes(preset.event_types);
  }

  async function savePreset() {
    if (!presetName.trim() || !nvrId || !areaName.trim() || !selectedChannels.length) return;
    try {
      const saved = await post<SearchPreset>("/search-presets", { name: presetName.trim(), nvr_id: nvrId, area_name: areaName.trim(), channel_ids: selectedChannels, event_types: eventTypes });
      await presets.refresh();
      setPresetId(saved.id);
      setPresetName("");
      setNotice({ tone: "success", text: "筛选条件已保存，下次可直接加载。" });
    } catch (caught) { setError(caught as ApiError); }
  }

  async function deletePreset() {
    if (!presetId) return;
    try {
      await api(`/search-presets/${presetId}`, { method: "DELETE" });
      setPresetId("");
      await presets.refresh();
      setNotice({ tone: "success", text: "历史筛选条件已删除。" });
    } catch (caught) { setError(caught as ApiError); }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!selectedChannels.length) { setNotice({ tone: "error", text: "请至少选择一个摄像机通道。" }); return; }
    setBusy(true); setError(null); setResults(null);
    try {
      const created = await post<Job>("/search-jobs", { nvr_id: nvrId, channel_ids: selectedChannels, from: localInputToRfc3339(from), to: localInputToRfc3339(to), source_modes: ["record_classification"], area_name: areaName.trim() || null, event_types: eventTypes, preset_id: presetId || null });
      setJob(created);
    } catch (caught) { setError(caught as ApiError); }
    finally { setBusy(false); }
  }

  async function generatePreview(bookmark: Bookmark) {
    try {
      let preview = await post<EventPreview>(`/bookmarks/${bookmark.id}/preview`);
      setPreviews((current) => ({ ...current, [bookmark.id]: preview }));
      while (["queued", "generating"].includes(preview.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        preview = await api<EventPreview>(`/bookmarks/${bookmark.id}/preview`);
        setPreviews((current) => ({ ...current, [bookmark.id]: preview }));
      }
      if (preview.status === "failed") setNotice({ tone: "error", text: "无法从该录像生成预览图，可直接生成候选片段确认。" });
    } catch (caught) { setError(caught as ApiError); }
  }

  async function createCandidate(bookmark: Bookmark) {
    try {
      await post("/clips", { bookmark_id: bookmark.id, search_job_id: results?.job_id ?? null, window_override: { pre_roll_ms: 5000, post_roll_ms: 10000, max_duration_ms: 30000 }, audio_policy: "prefer" });
      setNotice({ tone: "success", text: "候选视频正在生成，可到“候选与导出”查看进度。" });
    } catch (caught) { setError(caught as ApiError); }
  }

  if (!nvrs.loading && nvrs.data?.length === 0) return <><Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="先添加 NVR，然后用时间、目标区域和事件标签缩小录像范围。" /><Empty title="还没有可检索的 NVR" description="设备中心会自动搜索局域网内的 ONVIF/海康 ISAPI 候选设备，也保留手动地址输入。" action={<Button variant="primary" onClick={() => navigate("devices")}>前往设备中心</Button>} /></>;

  return <>
    <Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="输入时间和业务区域，组合摄像机与 NVR 事件标签，先看事件预览，再生成候选视频。" action={<Button onClick={() => navigate("exports")}>查看候选与导出</Button>} />
    <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-950"><strong>证据边界：</strong>当前结果来自 NVR 自身录像分类，不等同于经过人工验证的高置信事件。区域是你保存的业务别名，映射到摄像机集合与事件标签，不会虚构画面内的精确坐标。</div>
    <Problem error={error ?? nvrs.error ?? presets.error} />
    <form onSubmit={search} className={`${card} p-5 sm:p-7`}>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="text-sm font-semibold text-slate-700">录像设备<select required className={`${field} mt-2`} value={nvrId} onChange={(event) => { setNvrId(event.target.value); setSelectedChannels([]); setPresetId(""); }}>{nvrs.data?.map((nvr) => <option key={nvr.id} value={nvr.id}>{nvr.name}</option>)}</select></label>
        <label className="text-sm font-semibold text-slate-700">目标区域<input className={`${field} mt-2`} value={areaName} onChange={(event) => setAreaName(event.target.value)} placeholder="例如：一楼大厅 / 北侧车道" /></label>
        <label className="text-sm font-semibold text-slate-700">开始时间<input required type="datetime-local" className={`${field} mt-2`} value={from} onChange={(event) => setFrom(event.target.value)} /></label>
        <label className="text-sm font-semibold text-slate-700">结束时间<input required type="datetime-local" className={`${field} mt-2`} value={to} onChange={(event) => setTo(event.target.value)} /></label>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_.8fr]">
        <fieldset><legend className="mb-3 text-sm font-semibold text-slate-700">摄像机范围</legend><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{channels.map((channel) => <label key={channel.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm ${selectedChannels.includes(channel.id) ? "border-emerald-500 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}><input type="checkbox" checked={selectedChannels.includes(channel.id)} onChange={() => setSelectedChannels((current) => current.includes(channel.id) ? current.filter((id) => id !== channel.id) : [...current, channel.id])} /><span><strong className="block">{channel.alias || channel.device_name}</strong><small className={channel.online ? "text-emerald-700" : "text-slate-500"}>{channel.online ? "在线" : "状态未知/离线"}</small></span></label>)}</div></fieldset>
        <fieldset><legend className="mb-3 text-sm font-semibold text-slate-700">事件标签（不选则返回全部录像分类）</legend><div className="flex flex-wrap gap-2">{eventOptions.map((item) => <label key={item.id} className={`cursor-pointer rounded-full border px-3 py-2 text-xs font-semibold ${eventTypes.includes(item.id) ? "border-emerald-500 bg-emerald-100 text-emerald-900" : "border-slate-200 bg-white text-slate-600"}`}><input className="sr-only" type="checkbox" checked={eventTypes.includes(item.id)} onChange={() => setEventTypes((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.label}</label>)}</div></fieldset>
      </div>
      <div className="mt-6 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-5">
        <label className="min-w-56 text-xs font-semibold text-slate-600">加载历史筛选<select className={`${field} mt-1`} value={presetId} onChange={(event) => applyPreset(event.target.value)}><option value="">未加载</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name} · {preset.area_name}</option>)}</select></label>
        {presetId && <Button type="button" variant="ghost" onClick={deletePreset}>删除此筛选</Button>}
        <label className="min-w-56 text-xs font-semibold text-slate-600">保存当前筛选<input className={`${field} mt-1`} value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="例如：夜间北门车辆" /></label>
        <Button type="button" onClick={savePreset} disabled={!presetName.trim() || !areaName.trim() || !selectedChannels.length}>保存筛选</Button>
        <Button className="ml-auto" variant="primary" type="submit" disabled={busy || !nvrId}>{busy ? "提交中…" : "开始检索事件"}</Button>
      </div>
    </form>
    {job && <section className={`${card} mt-5 flex flex-wrap items-center gap-4 p-5`}><div className="min-w-48"><p className="text-xs font-semibold text-slate-500">检索任务</p><strong className="font-mono text-sm">{job.id}</strong></div>{["queued", "running"].includes(job.state) ? <Spinner label={`正在读取 NVR · ${Math.round(job.progress * 100)}%`} /> : <Badge tone={job.state === "succeeded" ? "positive" : "danger"}>{job.state}</Badge>}{job.error && <span className="text-sm text-red-700">{job.error.code} · {job.error.message}</span>}</section>}
    {results && <section className="mt-8"><div className="mb-4 flex items-end justify-between"><div><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">SEARCH RESULTS</p><h2 className="mt-1 text-2xl font-bold">找到 {results.items.length} 个事件/录像候选</h2></div>{selectedEvents.length > 0 && <Badge tone="positive">已选 {selectedEvents.length} 个</Badge>}</div>{results.items.length === 0 ? <Empty title="该条件下没有候选" description="可扩大时间范围、取消事件标签，或在设备中心检查事件与录像配置。" /> : <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{results.items.map((item) => <EventCard key={item.id} item={item} preview={previews[item.id]} selected={selectedEvents.includes(item.id)} onToggle={() => setSelectedEvents((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} onPreview={() => generatePreview(item)} onCandidate={() => createCandidate(item)} />)}</div>}</section>}
  </>;
}

function EventCard({ item, preview, selected, onToggle, onPreview, onCandidate }: { item: Bookmark; preview?: EventPreview; selected: boolean; onToggle: () => void; onPreview: () => void; onCandidate: () => void }) {
  const evidence = item.attributes.hikvision;
  return <article className={`${card} overflow-hidden ${selected ? "ring-2 ring-emerald-500" : ""}`}>
    <div className="relative aspect-video bg-[#142e29]">
      {preview?.status === "ready" && preview.content_url ? <img src={`${preview.content_url}?v=${encodeURIComponent(preview.job_id)}`} className="h-full w-full object-cover" alt={`${item.media_channel_label ?? "摄像机"}事件预览`} /> : <div className="grid h-full place-items-center text-center text-emerald-100/60"><div>{["queued", "generating"].includes(preview?.status ?? "") ? <Spinner label="读取录像帧" /> : <><div className="text-3xl">◫</div><p className="mt-2 text-xs">预览图按需从 NVR 生成</p></>}</div></div>}
      <label className="absolute left-3 top-3 flex cursor-pointer items-center gap-2 rounded-lg bg-black/60 px-3 py-2 text-xs font-semibold text-white backdrop-blur"><input type="checkbox" checked={selected} onChange={onToggle} />候选</label>
      <span className="absolute bottom-3 right-3 rounded-md bg-black/65 px-2 py-1 font-mono text-xs text-white">{formatDuration(item.start_at, item.end_at)}</span>
    </div>
    <div className="p-5"><div className="flex flex-wrap gap-2"><Badge>{eventLabel(evidence?.canonical_event_type)}</Badge>{evidence?.area_name && <Badge tone="warning">{evidence.area_name}</Badge>}</div><h3 className="mt-3 font-bold text-slate-950">{item.media_channel_label || item.source_channel.label}</h3><p className="mt-1 text-sm text-slate-600">{formatDateTime(item.start_at)} — {formatDateTime(item.end_at)}</p><dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-xs"><div><dt className="text-slate-500">NVR 原始分类</dt><dd className="mt-1 break-all font-mono text-slate-800">{evidence?.classification || "unknown"}</dd></div><div><dt className="text-slate-500">事件来源</dt><dd className="mt-1 text-slate-800">NVR 录像元数据</dd></div></dl><div className="mt-4 flex gap-2"><Button className="flex-1" onClick={onPreview} disabled={["queued", "generating"].includes(preview?.status ?? "")}>{preview?.status === "ready" ? "刷新预览" : "生成预览"}</Button><Button className="flex-1" variant="primary" onClick={onCandidate}>生成候选视频</Button></div><p className="mt-2 text-xs text-slate-500">候选视频含前后滚，最长 30 秒；原始事件时间仍完整保留。</p></div>
  </article>;
}

function eventLabel(value?: string) {
  return eventOptions.find((item) => item.id === value)?.label ?? "NVR 事件";
}
