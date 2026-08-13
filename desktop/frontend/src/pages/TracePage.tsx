import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, post } from "../api";
import { CameraSnapshot } from "../CameraSnapshot";
import { useLoad } from "../hooks";
import { dateToLocalInput, eventPresentation, formatDateTime, formatDuration, localInputToRfc3339 } from "../lib";
import type { View, NoticeSetter } from "../App";
import type { Bookmark, Channel, EventAnimation, EventPreview, Job, Nvr, SearchPreset, SearchResults } from "../types";
import { Badge, Button, Empty, Header, Problem, Spinner, card, field } from "../ui";

const eventOptions = [
  { id: "motion", label: "移动侦测" }, { id: "line_crossing", label: "越界侦测" },
  { id: "region_intrusion", label: "区域入侵" }, { id: "smart", label: "其他智能事件" },
  { id: "continuous", label: "连续录像" },
];
const PAGE_SIZE = 6;

export function TracePage({ navigate, setNotice }: { navigate: (view: View) => void; setNotice: NoticeSetter }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const presets = useLoad(() => api<SearchPreset[]>("/search-presets"));
  const [channelsByNvr, setChannelsByNvr] = useState<Record<string, Channel[]>>({});
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [presetId, setPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const now = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(dateToLocalInput(new Date(now.getTime() - 60 * 60 * 1000)));
  const [to, setTo] = useState(dateToLocalInput(now));
  const [jobs, setJobs] = useState<Job[]>([]);
  const [results, setResults] = useState<Bookmark[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [previews, setPreviews] = useState<Record<string, EventPreview>>({});
  const [animations, setAnimations] = useState<Record<string, EventAnimation>>({});
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);

  useEffect(() => { for (const nvr of nvrs.data ?? []) api<Channel[]>(`/nvrs/${nvr.id}/channels`).then((items) => setChannelsByNvr((current) => ({ ...current, [nvr.id]: items }))).catch((caught) => setError(caught as ApiError)); }, [nvrs.data]);
  useEffect(() => {
    if (!jobs.length || !jobs.some((job) => ["queued", "running"].includes(job.state))) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await Promise.all(jobs.map((job) => ["queued", "running"].includes(job.state) ? api<Job>(`/jobs/${job.id}`) : job));
        setJobs(next);
        if (next.every((job) => !["queued", "running"].includes(job.state))) await loadPage(next, 0);
      } catch (caught) { setError(caught as ApiError); }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [jobs]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadPage(currentJobs: Job[], nextPage: number) {
    const succeeded = currentJobs.filter((job) => job.state === "succeeded");
    const cumulativeLimit = Math.min(200, (nextPage + 1) * PAGE_SIZE);
    const pages = await Promise.all(succeeded.map((job) => api<SearchResults>(`/search-jobs/${job.id}/results?limit=${cumulativeLimit}&offset=0`)));
    const merged = pages.flatMap((value) => value.items).sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime()).slice(nextPage * PAGE_SIZE, (nextPage + 1) * PAGE_SIZE);
    setResults(merged); setTotal(pages.reduce((sum, value) => sum + value.total, 0)); setPage(nextPage); setSelectedEvents([]);
  }

  function applyPreset(id: string) { setPresetId(id); const preset = presets.data?.find((item) => item.id === id); if (!preset) return; setSelectedChannels(preset.channel_ids); setEventTypes(preset.event_types); }
  async function savePreset() { if (!presetName.trim() || !selectedChannels.length) return; try { const saved = await post<SearchPreset>("/search-presets", { name: presetName.trim(), channel_ids: selectedChannels, event_types: eventTypes }); await presets.refresh(); setPresetId(saved.id); setPresetName(""); setNotice({ tone: "success", text: "摄像机与行为筛选已保存，下次可直接加载。" }); } catch (caught) { setError(caught as ApiError); } }
  async function deletePreset() { if (!presetId) return; try { await api(`/search-presets/${presetId}`, { method: "DELETE" }); setPresetId(""); await presets.refresh(); setNotice({ tone: "success", text: "历史筛选条件已删除。" }); } catch (caught) { setError(caught as ApiError); } }
  async function search(event: FormEvent) {
    event.preventDefault(); if (!selectedChannels.length) { setNotice({ tone: "error", text: "请至少选择一个摄像机画面。" }); return; }
    setBusy(true); setError(null); setResults([]); setTotal(0); setPage(0); setPreviews({}); setAnimations({});
    try {
      const grouped = Object.entries(channelsByNvr).map(([nvrId, channels]) => ({ nvrId, channelIds: channels.filter((channel) => selectedChannels.includes(channel.id)).map((channel) => channel.id) })).filter((group) => group.channelIds.length);
      const created = await Promise.all(grouped.map((group) => post<Job>("/search-jobs", { nvr_id: group.nvrId, channel_ids: group.channelIds, from: localInputToRfc3339(from), to: localInputToRfc3339(to), source_modes: ["record_classification"], event_types: eventTypes, preset_id: presetId || null })));
      setJobs(created);
    } catch (caught) { setError(caught as ApiError); } finally { setBusy(false); }
  }

  async function createCandidate(item: Bookmark) { try { await post("/clips", { bookmark_id: item.id, search_job_id: item.attributes.hikvision?.search_job_id, window_override: { pre_roll_ms: 5_000, post_roll_ms: 10_000, max_duration_ms: 30_000 }, audio_policy: "prefer" }); setNotice({ tone: "success", text: "候选片段已进入导出队列。" }); } catch (caught) { setError(caught as ApiError); } }
  async function ensurePreview(item: Bookmark) { const existing = previews[item.id]; if (existing && existing.status !== "failed") return; try { let value = await post<EventPreview>(`/bookmarks/${item.id}/preview`); setPreviews((current) => ({ ...current, [item.id]: value })); for (let i = 0; i < 50 && ["queued", "generating"].includes(value.status); i += 1) { await new Promise((resolve) => window.setTimeout(resolve, 500)); value = await api<EventPreview>(`/bookmarks/${item.id}/preview`); setPreviews((current) => ({ ...current, [item.id]: value })); } } catch { /* keep the result card usable */ } }
  async function ensureAnimation(item: Bookmark) { const existing = animations[item.id]; if (existing && existing.status !== "failed") return; try { let value = await post<EventAnimation>(`/bookmarks/${item.id}/animation`); setAnimations((current) => ({ ...current, [item.id]: value })); for (let i = 0; i < 70 && ["queued", "generating"].includes(value.status); i += 1) { await new Promise((resolve) => window.setTimeout(resolve, 500)); value = await api<EventAnimation>(`/bookmarks/${item.id}/animation`); setAnimations((current) => ({ ...current, [item.id]: value })); } } catch { /* static preview remains */ } }

  useEffect(() => { for (const item of results) void ensurePreview(item); }, [results]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!nvrs.loading && nvrs.data?.length === 0) return <><Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="先添加 NVR，再用时间、摄像机画面和目标行为缩小录像范围。" /><Empty title="还没有可检索的 NVR" description="请先在设备中心添加设备。" action={<Button variant="primary" onClick={() => navigate("devices")}>前往设备中心</Button>} /></>;
  const working = jobs.some((job) => ["queued", "running"].includes(job.state));
  const channels = Object.values(channelsByNvr).flat();
  const cameraName = (channelId: string | null, fallback: string) => {
    const channel = channels.find((item) => item.id === channelId);
    return channel?.alias || (channel ? `未命名摄像机 · 通道 ${channel.external_channel_id}` : fallback.replace(/^Channel\s*/i, "未命名摄像机 · 通道 "));
  };

  return <>
    <Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="选择时间、看得懂的摄像机画面和目标行为；TraceCue 会跨 NVR 检索并自动生成可视预览。" action={<Button onClick={() => navigate("exports")}>查看候选与导出</Button>} />
    <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-5 py-3 text-sm text-amber-950"><strong>证据边界：</strong>结果来自 NVR 录像分类；目标区域就是你选择的摄像机画面，不再使用无实际筛选字段的自由文本标签。</div>
    <Problem error={error ?? nvrs.error ?? presets.error} />
    <form onSubmit={search} className={`${card} p-5 sm:p-7`}><div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold text-slate-700">开始时间<input required type="datetime-local" className={`${field} mt-2`} value={from} onChange={(event) => setFrom(event.target.value)} /></label><label className="text-sm font-semibold text-slate-700">结束时间<input required type="datetime-local" className={`${field} mt-2`} value={to} onChange={(event) => setTo(event.target.value)} /></label></div><fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">目标区域 · 选择摄像机画面</legend><div className="space-y-5">{nvrs.data?.map((nvr) => <div key={nvr.id}><h3 className="mb-2 text-sm font-bold">{nvr.name}</h3><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{(channelsByNvr[nvr.id] ?? []).map((channel) => <label key={channel.id} className={`cursor-pointer overflow-hidden rounded-2xl border bg-white transition ${selectedChannels.includes(channel.id) ? "border-emerald-500 ring-2 ring-emerald-200" : "border-slate-200"}`}><div className="relative"><CameraSnapshot channel={channel} /><input className="absolute left-3 top-3 h-5 w-5 accent-emerald-700" type="checkbox" checked={selectedChannels.includes(channel.id)} onChange={() => setSelectedChannels((current) => current.includes(channel.id) ? current.filter((id) => id !== channel.id) : [...current, channel.id])} /></div><div className="p-3"><strong className="block text-sm">{channel.alias || "未命名摄像机"}</strong><small className="text-slate-500">{channel.online ? "在线" : "状态未知/离线"} · 通道 {channel.external_channel_id}</small></div></label>)}</div></div>)}</div></fieldset><fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">目标行为（不选则返回全部录像分类）</legend><div className="flex flex-wrap gap-2">{eventOptions.map((item) => <label key={item.id} className={`cursor-pointer rounded-full border px-3 py-2 text-xs font-semibold ${eventTypes.includes(item.id) ? "border-emerald-500 bg-emerald-100 text-emerald-900" : "border-slate-200 bg-white text-slate-600"}`}><input className="sr-only" type="checkbox" checked={eventTypes.includes(item.id)} onChange={() => setEventTypes((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.label}</label>)}</div></fieldset><div className="mt-6 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-5"><label className="min-w-56 text-xs font-semibold text-slate-600">加载历史筛选<select className={`${field} mt-1`} value={presetId} onChange={(event) => applyPreset(event.target.value)}><option value="">未加载</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>{presetId && <Button type="button" variant="ghost" onClick={deletePreset}>删除此筛选</Button>}<label className="min-w-56 text-xs font-semibold text-slate-600">保存当前筛选<input className={`${field} mt-1`} value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="例如：夜间入口车辆" /></label><Button type="button" onClick={savePreset} disabled={!presetName.trim() || !selectedChannels.length}>保存筛选</Button><Button className="ml-auto" variant="primary" type="submit" disabled={busy || !selectedChannels.length}>{busy ? "提交中…" : "开始检索事件"}</Button></div></form>
    {jobs.length > 0 && <section className={`${card} mt-5 flex flex-wrap items-center gap-4 p-5`}>{working ? <Spinner label={`正在读取 ${jobs.length} 台 NVR`} /> : <Badge tone={jobs.every((job) => job.state === "succeeded") ? "positive" : "warning"}>{jobs.filter((job) => job.state === "succeeded").length}/{jobs.length} 个检索已完成</Badge>}{jobs.flatMap((job) => job.error ? [<span key={job.id} className="text-sm text-red-700">{job.error.code} · {job.error.message}</span>] : [])}</section>}
    {!working && jobs.length > 0 && <section className="mt-8"><div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">SEARCH RESULTS</p><h2 className="mt-1 text-2xl font-bold">找到 {total} 个录像候选</h2></div><div className="flex items-center gap-2"><Button disabled={page === 0} onClick={() => loadPage(jobs, page - 1)}>上一页</Button><Badge>第 {page + 1} 页</Badge><Button disabled={(page + 1) * PAGE_SIZE >= total || (page + 1) * PAGE_SIZE >= 200 * Math.max(1, jobs.length)} onClick={() => loadPage(jobs, page + 1)}>下一页</Button></div></div>{results.length === 0 ? <Empty title="该条件下没有候选" description="可扩大时间范围、取消行为筛选，或在设备中心检查事件与录像配置。" /> : <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{results.map((item) => <EventCard key={item.id} item={item} cameraName={cameraName(item.media_channel_id, item.media_channel_label || item.source_channel.label)} preview={previews[item.id]} animation={animations[item.id]} selected={selectedEvents.includes(item.id)} onHover={() => ensureAnimation(item)} onToggle={() => setSelectedEvents((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} onCandidate={() => createCandidate(item)} />)}</div>}</section>}
  </>;
}

function EventCard({ item, cameraName, preview, animation, selected, onHover, onToggle, onCandidate }: { item: Bookmark; cameraName: string; preview?: EventPreview; animation?: EventAnimation; selected: boolean; onHover: () => void; onToggle: () => void; onCandidate: () => void }) {
  const [hovering, setHovering] = useState(false); const evidence = item.attributes.hikvision; const image = hovering && animation?.status === "ready" ? animation : preview;
  return <article className={`${card} overflow-hidden ${selected ? "ring-2 ring-emerald-500" : ""}`}><div className="relative aspect-video bg-[#142e29]" onMouseEnter={() => { setHovering(true); onHover(); }} onMouseLeave={() => setHovering(false)}>{image?.status === "ready" && image.content_url ? <img src={`${image.content_url}?v=${encodeURIComponent(image.job_id)}`} className="h-full w-full object-cover" alt={`${cameraName}事件预览`} /> : <div className="grid h-full place-items-center text-emerald-100/70"><Spinner label={hovering ? "生成 3 秒悬停预览" : "自动读取事件画面"} /></div>}<label className="absolute left-3 top-3 flex cursor-pointer items-center gap-2 rounded-lg bg-black/60 px-3 py-2 text-xs font-semibold text-white"><input type="checkbox" checked={selected} onChange={onToggle} />候选</label><span className="absolute bottom-3 right-3 rounded-md bg-black/65 px-2 py-1 font-mono text-xs text-white">{formatDuration(item.start_at, item.end_at)}</span></div><div className="p-5"><Badge>{eventPresentation(evidence?.canonical_event_type || item.event_type)}</Badge><h3 className="mt-3 font-bold">{cameraName}</h3><p className="mt-1 text-sm text-slate-600">{formatDateTime(item.start_at)} — {formatDateTime(item.end_at)}</p><p className="mt-3 text-xs leading-5 text-slate-500">来源：NVR 录像元数据。移入画面可播放缓存的 3 秒预览。</p><Button className="mt-4 w-full" variant="primary" onClick={onCandidate}>生成候选视频</Button></div></article>;
}
