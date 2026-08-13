import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, patch, post } from "../api";
import { CameraSnapshot } from "../CameraSnapshot";
import { useLoad } from "../hooks";
import {
  dateToLocalInput,
  eventDefinitions,
  eventPresentation,
  formatDateTime,
  lastNightWindow,
  timeWindowLabel,
  type TimeWindow,
} from "../lib";
import type { View, NoticeSetter } from "../App";
import type {
  AppSettings,
  Bookmark,
  Channel,
  DurationClass,
  EventAnimation,
  EventAudit,
  EventPreview,
  Nvr,
  ReviewFilter,
  ReviewState,
  SearchPreset,
  TraceDensityBucket,
  TraceSession,
  TraceSessionResults,
} from "../types";
import { Badge, Button, Empty, Header, Problem, Spinner, card, field } from "../ui";

const PAGE_SIZE = 6;
const reviewFilters: { id: ReviewFilter; label: string }[] = [
  { id: "active", label: "待筛选" },
  { id: "unreviewed", label: "未查看" },
  { id: "reviewed", label: "已查看" },
  { id: "candidate", label: "候选" },
  { id: "excluded", label: "已排除" },
  { id: "all", label: "全部" },
];
const durationOptions: { id: DurationClass; label: string }[] = [
  { id: "under_5s", label: "短于 5 秒" },
  { id: "5_to_30s", label: "5–30 秒" },
  { id: "over_30s", label: "长于 30 秒" },
  { id: "unknown", label: "时长未知" },
];

function inputWindow(from: string, to: string): TimeWindow {
  return { from: new Date(from), to: new Date(to) };
}

function exactWindow(from: string, to: string) {
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  });
  return `${formatter.format(new Date(from))} – ${formatter.format(new Date(to))}`;
}

export function TracePage({ navigate, setNotice }: { navigate: (view: View) => void; setNotice: NoticeSetter }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const presets = useLoad(() => api<SearchPreset[]>("/search-presets"));
  const settings = useLoad(() => api<AppSettings>("/settings"));
  const defaultWindow = useMemo(() => lastNightWindow(new Date()), []);
  const [channelsByNvr, setChannelsByNvr] = useState<Record<string, Channel[]>>({});
  const [auditsByNvr, setAuditsByNvr] = useState<Record<string, EventAudit>>({});
  const [selectedChannel, setSelectedChannel] = useState("");
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [presetId, setPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const [from, setFrom] = useState(dateToLocalInput(defaultWindow.from));
  const [to, setTo] = useState(dateToLocalInput(defaultWindow.to));
  const [activeSession, setActiveSession] = useState<TraceSession | null>(null);
  const [results, setResults] = useState<TraceSessionResults | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("active");
  const [page, setPage] = useState(0);
  const [focusBucket, setFocusBucket] = useState<TraceDensityBucket | null>(null);
  const [durationClass, setDurationClass] = useState<DurationClass | null>(null);
  const [focusEventType, setFocusEventType] = useState<string | null>(null);
  const [secondaryActive, setSecondaryActive] = useState(false);
  const [timeTouched, setTimeTouched] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [previews, setPreviews] = useState<Record<string, EventPreview>>({});
  const [animations, setAnimations] = useState<Record<string, EventAnimation>>({});

  useEffect(() => {
    for (const nvr of nvrs.data ?? []) {
      api<Channel[]>(`/nvrs/${nvr.id}/channels`)
        .then((items) => setChannelsByNvr((current) => ({ ...current, [nvr.id]: items })))
        .catch((caught) => setError(caught as ApiError));
      api<EventAudit>(`/nvrs/${nvr.id}/event-audit`)
        .then((audit) => setAuditsByNvr((current) => ({ ...current, [nvr.id]: audit })))
        .catch(() => undefined);
    }
  }, [nvrs.data]);

  useEffect(() => {
    if (!settings.data || timeTouched || activeSession) return;
    const value = lastNightWindow(new Date(), settings.data.night_start_hour, settings.data.night_end_hour);
    setFrom(dateToLocalInput(value.from));
    setTo(dateToLocalInput(value.to));
  }, [settings.data, timeTouched, activeSession]);

  const channels = useMemo(() => Object.values(channelsByNvr).flat(), [channelsByNvr]);
  const eligibleChannelIds = useMemo(() => new Set(channels.filter((channel) => {
    if (!eventTypes.length) return true;
    const audit = auditsByNvr[channel.nvr_id];
    if (!audit) return true;
    return eventTypes.every((eventType) => audit.rules.some((rule) =>
      rule.channel_external_id === channel.external_channel_id
      && rule.event_type === eventType
      && rule.state === "supported",
    ));
  }).map((channel) => channel.id)), [channels, auditsByNvr, eventTypes]);

  useEffect(() => {
    if (selectedChannel && !eligibleChannelIds.has(selectedChannel)) setSelectedChannel("");
  }, [eligibleChannelIds, selectedChannel]);

  const working = activeSession?.iterations.some((iteration) =>
    iteration.jobs.some((job) => ["queued", "running"].includes(job.state)),
  ) ?? false;
  const windowValue = inputWindow(from, to);
  const validWindow = !Number.isNaN(windowValue.from.getTime())
    && !Number.isNaN(windowValue.to.getTime()) && windowValue.to > windowValue.from;
  const primaryReady = Boolean(selectedChannel && eventTypes.length && validWindow);

  function cameraName(channelId: string | null, fallback: string) {
    const channel = channels.find((item) => item.id === channelId);
    return channel?.alias || channel?.device_name
      || fallback.replace(/^Channel\s*/i, "未命名摄像机 · 通道 ");
  }

  function capableCameraCount(eventType: string) {
    return channels.filter((channel) => auditsByNvr[channel.nvr_id]?.rules.some((rule) =>
      rule.channel_external_id === channel.external_channel_id
      && rule.event_type === eventType
      && rule.state === "supported",
    )).length;
  }

  async function loadResults(
    sessionId: string,
    options: {
      summary?: boolean;
      nextPage?: number;
      nextFilter?: ReviewFilter;
      bucket?: TraceDensityBucket | null;
      duration?: DurationClass | null;
      eventType?: string | null;
    } = {},
  ) {
    const summary = options.summary ?? !secondaryActive;
    const nextPage = options.nextPage ?? page;
    const nextFilter = options.nextFilter ?? reviewFilter;
    const bucket = options.bucket === undefined ? focusBucket : options.bucket;
    const duration = options.duration === undefined ? durationClass : options.duration;
    const eventType = options.eventType === undefined ? focusEventType : options.eventType;
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE), offset: String(nextPage * PAGE_SIZE), review_state: nextFilter,
      summary_only: String(summary),
    });
    if (bucket) {
      query.set("from", bucket.start_at);
      query.set("to", bucket.end_at);
    }
    if (duration) query.set("duration_class", duration);
    if (eventType) query.set("event_type", eventType);
    const value = await api<TraceSessionResults>(`/trace-sessions/${sessionId}/results?${query}`);
    setResults(value);
    setPage(nextPage);
  }

  useEffect(() => {
    if (!activeSession || !working) return;
    const timer = window.setTimeout(async () => {
      try {
        const refreshed = await api<TraceSession>(`/trace-sessions/${activeSession.id}`);
        setActiveSession(refreshed);
        await loadResults(refreshed.id, { summary: !secondaryActive });
      } catch (caught) {
        setError(caught as ApiError);
      }
    }, 800);
    return () => window.clearTimeout(timer);
  }, [activeSession, working, secondaryActive, page, reviewFilter, focusBucket, durationClass, focusEventType]); // eslint-disable-line react-hooks/exhaustive-deps

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!primaryReady) {
      setNotice({ tone: "error", text: "请选择一个摄像机、至少一种事件类型和有效时间范围。" });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let session = await post<TraceSession>("/trace-sessions", {
        channel_ids: [selectedChannel], event_types: eventTypes, preset_id: presetId || null,
      });
      session = await post<TraceSession>(`/trace-sessions/${session.id}/iterations`, {
        from: windowValue.from.toISOString(), to: windowValue.to.toISOString(),
        label: `时间范围 · ${timeWindowLabel(windowValue)}`,
      });
      setActiveSession(session);
      setReviewFilter("active");
      setFocusBucket(null);
      setDurationClass(null);
      setFocusEventType(null);
      setSecondaryActive(false);
      await loadResults(session.id, {
        summary: true, nextPage: 0, nextFilter: "active", bucket: null, duration: null, eventType: null,
      });
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setBusy(false);
    }
  }

  function setQuickWindow(value: TimeWindow) {
    setFrom(dateToLocalInput(value.from));
    setTo(dateToLocalInput(value.to));
    setTimeTouched(true);
  }

  function applyPreset(id: string) {
    setPresetId(id);
    const preset = presets.data?.find((item) => item.id === id);
    if (!preset) return;
    setSelectedChannel(preset.channel_ids[0] ?? "");
    setEventTypes(preset.event_types.filter((value) => eventDefinitions.some((item) => item.id === value)));
  }

  async function savePreset() {
    if (!presetName.trim() || !selectedChannel || !eventTypes.length) return;
    try {
      const saved = await post<SearchPreset>("/search-presets", {
        name: presetName.trim(), channel_ids: [selectedChannel], event_types: eventTypes,
      });
      await presets.refresh();
      setPresetId(saved.id);
      setPresetName("");
      setNotice({ tone: "success", text: "摄像机与事件类型已保存，下次可直接加载。" });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function deletePreset() {
    if (!presetId) return;
    try {
      await api(`/search-presets/${presetId}`, { method: "DELETE" });
      setPresetId("");
      await presets.refresh();
      setNotice({ tone: "success", text: "历史筛选条件已删除。" });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function showResults(options: {
    bucket?: TraceDensityBucket | null; duration?: DurationClass | null; eventType?: string | null;
  } = {}) {
    if (!activeSession) return;
    const bucket = options.bucket === undefined ? focusBucket : options.bucket;
    const duration = options.duration === undefined ? durationClass : options.duration;
    const eventType = options.eventType === undefined ? focusEventType : options.eventType;
    setFocusBucket(bucket);
    setDurationClass(duration);
    setFocusEventType(eventType);
    setSecondaryActive(true);
    try {
      await loadResults(activeSession.id, {
        summary: false, nextPage: 0, bucket, duration, eventType,
      });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function resetSecondary() {
    if (!activeSession) return;
    setSecondaryActive(false);
    setFocusBucket(null);
    setDurationClass(null);
    setFocusEventType(null);
    setReviewFilter("active");
    try {
      await loadResults(activeSession.id, {
        summary: true, nextPage: 0, nextFilter: "active", bucket: null, duration: null, eventType: null,
      });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function chooseReviewFilter(next: ReviewFilter) {
    if (!activeSession) return;
    setReviewFilter(next);
    try { await loadResults(activeSession.id, { summary: false, nextPage: 0, nextFilter: next }); }
    catch (caught) { setError(caught as ApiError); }
  }

  async function changeReview(item: Bookmark, state: ReviewState) {
    if (!activeSession) return;
    try {
      await patch(`/trace-sessions/${activeSession.id}/events/${item.id}`, { state });
      await loadResults(activeSession.id, { summary: false });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function createCandidate(item: Bookmark) {
    if (!activeSession || !item.search_job_id) return;
    try {
      await post("/clips", {
        bookmark_id: item.id,
        search_job_id: item.search_job_id,
        window_override: { pre_roll_ms: 5_000, post_roll_ms: 10_000, max_duration_ms: 60_000 },
        audio_policy: "prefer",
      });
      await patch(`/trace-sessions/${activeSession.id}/events/${item.id}`, { state: "candidate" });
      await loadResults(activeSession.id, { summary: false });
      setNotice({ tone: "success", text: "事件已加入候选，视频片段正在后台生成。" });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  async function ensurePreview(item: Bookmark) {
    const existing = previews[item.id];
    if (existing && existing.status !== "failed") return;
    try {
      let value = await post<EventPreview>(`/bookmarks/${item.id}/preview`);
      setPreviews((current) => ({ ...current, [item.id]: value }));
      for (let index = 0; index < 50 && ["queued", "generating"].includes(value.status); index += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        value = await api<EventPreview>(`/bookmarks/${item.id}/preview`);
        setPreviews((current) => ({ ...current, [item.id]: value }));
      }
    } catch { /* Result metadata remains usable when preview generation is unavailable. */ }
  }

  async function ensureAnimation(item: Bookmark) {
    const existing = animations[item.id];
    if (existing && existing.status !== "failed") return;
    try {
      let value = await post<EventAnimation>(`/bookmarks/${item.id}/animation`);
      setAnimations((current) => ({ ...current, [item.id]: value }));
      for (let index = 0; index < 70 && ["queued", "generating"].includes(value.status); index += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        value = await api<EventAnimation>(`/bookmarks/${item.id}/animation`);
        setAnimations((current) => ({ ...current, [item.id]: value }));
      }
    } catch { /* Static preview remains available. */ }
  }

  useEffect(() => {
    if (!secondaryActive) return;
    for (const item of results?.items ?? []) void ensurePreview(item);
  }, [secondaryActive, results?.items]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!nvrs.loading && nvrs.data?.length === 0) {
    return <><Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="先添加 NVR，再用时间、单个摄像机画面和事件类型检索目标录像。" /><Empty title="还没有可检索的 NVR" description="请先在设备中心添加设备。" action={<Button variant="primary" onClick={() => navigate("devices")}>前往设备中心</Button>} /></>;
  }

  const groupedResults = Object.entries(
    (results?.items ?? []).reduce<Record<string, Bookmark[]>>((groups, item) => {
      const key = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date(item.start_at));
      (groups[key] ??= []).push(item);
      return groups;
    }, {}),
  );
  const maxDensity = Math.max(1, ...(results?.density ?? []).map((item) => item.count));
  const selectedIteration = activeSession?.iterations[0];

  return <>
    <Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="先检索一个摄像机的事件统计，再用事件密度、时长或类型缩小范围；只有确认二次筛选后才加载事件画面。" action={<Button onClick={() => navigate("exports")}>查看候选与导出</Button>} />
    <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-5 py-3 text-sm leading-6 text-amber-950"><strong>证据边界：</strong>TraceCue 读取 NVR 已保存的事件日志。事件时长来自开始/停止日志配对；不能配对时显示“时长未知”，不会再伪装成 1 秒。</div>
    <Problem error={error ?? nvrs.error ?? presets.error ?? settings.error} />

    <form onSubmit={search} className={`${card} p-5 sm:p-7`}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-56 flex-1 text-sm font-semibold text-slate-700">开始时间<input required type="datetime-local" className={`${field} mt-2`} value={from} onChange={(event) => { setFrom(event.target.value); setTimeTouched(true); }} /></label>
        <label className="min-w-56 flex-1 text-sm font-semibold text-slate-700">结束时间<input required type="datetime-local" className={`${field} mt-2`} value={to} onChange={(event) => { setTo(event.target.value); setTimeTouched(true); }} /></label>
        <Button type="button" onClick={() => setQuickWindow(lastNightWindow(new Date(), settings.data?.night_start_hour ?? 18, settings.data?.night_end_hour ?? 6))}>填入昨晚</Button>
      </div>

      <fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">1. 选择事件类型</legend><p className="mb-3 text-xs leading-5 text-slate-500">至少选择一种。选择 Smart 事件后，只显示已由设备接口证明具备全部所选能力的摄像机；连续录像不是事件筛选项。</p><div className="grid gap-3 md:grid-cols-2">
        {(["ordinary", "smart"] as const).map((category) => <div key={category} className={`rounded-xl border p-4 ${category === "smart" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-slate-50"}`}><strong className="mb-3 block text-sm">{category === "smart" ? "Smart 事件 · 设备相关" : "普通事件 · 基础能力"}</strong><div className="flex flex-wrap gap-2">{eventDefinitions.filter((item) => item.category === category).map((item) => <label key={item.id} className={`cursor-pointer rounded-full border px-3 py-2 text-xs font-semibold ${eventTypes.includes(item.id) ? "border-emerald-500 bg-emerald-100 text-emerald-900" : "border-slate-200 bg-white text-slate-600"}`}><input className="sr-only" type="checkbox" checked={eventTypes.includes(item.id)} onChange={() => setEventTypes((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.label} · {capableCameraCount(item.id)} 台</label>)}</div></div>)}
      </div></fieldset>

      <fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">2. 选择一个摄像机</legend><div className="space-y-5">
        {nvrs.data?.map((nvr) => { const visibleChannels = (channelsByNvr[nvr.id] ?? []).filter((channel) => eligibleChannelIds.has(channel.id)); return <div key={nvr.id}><h3 className="mb-2 text-sm font-bold">{nvr.name} <span className="font-normal text-slate-500">· {visibleChannels.length} 台可用</span></h3>{visibleChannels.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visibleChannels.map((channel) => <label key={channel.id} className={`cursor-pointer overflow-hidden rounded-2xl border bg-white transition ${selectedChannel === channel.id ? "border-emerald-500 ring-2 ring-emerald-200" : "border-slate-200"}`}><div className="relative"><CameraSnapshot channel={channel} /><input className="absolute left-3 top-3 h-5 w-5 accent-emerald-700" type="radio" name="trace-camera" checked={selectedChannel === channel.id} onChange={() => setSelectedChannel(channel.id)} /></div><div className="p-3"><strong className="block text-sm">{channel.alias || channel.device_name || "未命名摄像机"}</strong><small className="text-slate-500">{channel.online ? "在线" : "状态未知 / 离线"} · 通道 {channel.external_channel_id}</small></div></label>)}
        </div> : <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">这台 NVR 没有摄像机具备当前所选的全部事件能力。可到设备中心重新扫描事件配置。</div>}</div>; })}
      </div></fieldset>

      <div className="mt-6 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-5">
        <label className="min-w-56 text-xs font-semibold text-slate-600">加载常用筛选<select className={`${field} mt-1`} value={presetId} onChange={(event) => applyPreset(event.target.value)}><option value="">未加载</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        {presetId && <Button type="button" variant="ghost" onClick={deletePreset}>删除此筛选</Button>}
        <label className="min-w-56 text-xs font-semibold text-slate-600">保存当前筛选<input className={`${field} mt-1`} value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="例如：夜间门口越界" /></label>
        <Button type="button" onClick={savePreset} disabled={!presetName.trim() || !selectedChannel || !eventTypes.length}>保存筛选</Button>
        <Button className="ml-auto" variant="primary" type="submit" disabled={busy || !primaryReady}>{busy ? "提交中…" : "检索事件统计"}</Button>
      </div>
    </form>

    {activeSession && <section className={`${card} mt-5 p-5`}>
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">PRIMARY SEARCH</p><h2 className="mt-1 text-xl font-bold">本次检索</h2></div>{selectedIteration && <Badge tone={working ? "warning" : selectedIteration.state === "succeeded" ? "positive" : "danger"}>{working ? "检索中" : selectedIteration.state === "succeeded" ? "统计完成" : "检索失败"}</Badge>}</div>
      <div className="mt-3 flex flex-wrap gap-2"><Badge>{cameraName(activeSession.channel_ids[0] ?? null, activeSession.channel_ids[0] ?? "")}</Badge>{activeSession.event_types.map((type) => <Badge key={type}>{eventPresentation(type)}</Badge>)}</div>
      {selectedIteration && <p className="mt-3 text-sm text-slate-600">{exactWindow(selectedIteration.from, selectedIteration.to)} · {selectedIteration.result_count} 个事件</p>}
      {selectedIteration?.jobs.flatMap((job) => job.error ? [<p key={job.id} className="mt-2 text-xs text-red-700">{job.error.code} · {job.error.message}</p>] : [])}
      {working && <div className="mt-3"><Spinner label="正在从 NVR 读取事件统计；完成前不会加载事件画面" /></div>}
    </section>}

    {activeSession && results && !working && <section className="mt-8">
      <div className="mb-4"><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">SECONDARY FILTER</p><h2 className="mt-1 text-2xl font-bold">用事件统计缩小范围</h2><p className="mt-1 text-sm text-slate-500">共 {Object.values(results.counts).reduce((sum, value) => sum + value, 0)} 个事件。点击一个统计条件后，才加载事件列表与预览图。</p></div>

      {Object.values(results.counts).reduce((sum, value) => sum + value, 0) === 0 ? <Empty title="这个时间范围没有返回事件" description="请修改上方时间范围、摄像机或事件类型，再发起一次新的检索。" /> : <div className={`${card} mb-5 p-5`}>
        {results.density.length > 0 && <div><strong className="text-sm">事件密度 · 点击时间桶查看事件</strong><div className="mt-3 flex min-h-24 items-end gap-1 overflow-x-auto rounded-xl bg-slate-50 p-3">{results.density.map((bucket) => <button type="button" key={bucket.start_at} title={`${formatDateTime(bucket.start_at)} · ${bucket.count} 个事件`} aria-label={`${formatDateTime(bucket.start_at)}，${bucket.count} 个事件`} onClick={() => void showResults({ bucket })} className={`min-w-7 rounded-t transition ${focusBucket?.start_at === bucket.start_at ? "bg-amber-500" : "bg-emerald-600 hover:bg-emerald-500"}`} style={{ height: `${Math.max(12, Math.round(bucket.count / maxDensity * 72))}px` }}><span className="sr-only">{bucket.count}</span></button>)}</div></div>}
        <div className="mt-5"><strong className="text-sm">事件时长</strong><div className="mt-2 flex flex-wrap gap-2">{durationOptions.filter((option) => results.duration_buckets[option.id] > 0).map((option) => <button type="button" key={option.id} onClick={() => void showResults({ duration: option.id })} className={`rounded-full border px-3 py-2 text-xs font-semibold ${durationClass === option.id ? "border-amber-500 bg-amber-100 text-amber-900" : "border-slate-200 bg-white text-slate-600"}`}>{option.label} {results.duration_buckets[option.id]}</button>)}</div></div>
        {Object.values(results.event_type_counts).filter((count) => count > 0).length > 1 && <div className="mt-5"><strong className="text-sm">事件类型构成</strong><div className="mt-2 flex flex-wrap gap-2">{Object.entries(results.event_type_counts).filter(([, count]) => count > 0).map(([type, count]) => <button type="button" key={type} onClick={() => void showResults({ eventType: type })} className={`rounded-full border px-3 py-2 text-xs font-semibold ${focusEventType === type ? "border-amber-500 bg-amber-100 text-amber-900" : "border-slate-200 bg-white text-slate-600"}`}>{eventPresentation(type)} {count}</button>)}</div></div>}
        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4"><Button variant="primary" onClick={() => void showResults()}>查看全部事件</Button>{secondaryActive && <Button onClick={() => void resetSecondary()}>返回统计，不加载画面</Button>}</div>
      </div>}

      {secondaryActive && <>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-2xl font-bold">筛选后 {results.total} 个事件</h2><p className="mt-1 text-sm text-slate-500">每页只加载 {PAGE_SIZE} 个事件画面。</p></div><div className="flex items-center gap-2"><Button disabled={page === 0} onClick={() => activeSession && void loadResults(activeSession.id, { summary: false, nextPage: page - 1 })}>上一页</Button><Badge>第 {page + 1} 页</Badge><Button disabled={!results.has_more} onClick={() => activeSession && void loadResults(activeSession.id, { summary: false, nextPage: page + 1 })}>下一页</Button></div></div>
        <div className={`${card} mb-5 p-4`}><div className="flex flex-wrap gap-2">{reviewFilters.map((filter) => {
          const count = filter.id === "all" ? Object.values(results.counts).reduce((sum, value) => sum + value, 0)
            : filter.id === "active" ? results.counts.unreviewed + results.counts.reviewed + results.counts.candidate
              : results.counts[filter.id];
          return <button type="button" key={filter.id} onClick={() => void chooseReviewFilter(filter.id)} className={`rounded-full border px-3 py-2 text-xs font-semibold ${reviewFilter === filter.id ? "border-emerald-600 bg-emerald-700 text-white" : "border-slate-200 bg-white text-slate-600"}`}>{filter.label} {count}</button>;
        })}</div></div>
        {results.items.length === 0 ? <Empty title="当前二次筛选没有事件" description="请选择其他密度时间桶、时长或事件类型。" /> : groupedResults.map(([date, items]) => <div key={date} className="mb-7"><h3 className="mb-3 text-lg font-bold">{date}</h3><div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{items.map((item) => <EventCard key={item.id} item={item} cameraName={cameraName(item.media_channel_id, item.media_channel_label || item.source_channel.label)} preview={previews[item.id]} animation={animations[item.id]} onHover={() => ensureAnimation(item)} onReview={(state) => changeReview(item, state)} onCandidate={() => createCandidate(item)} />)}</div></div>)}
      </>}
    </section>}
  </>;
}

function reviewPresentation(state: ReviewState) {
  if (state === "candidate") return { label: "已加入候选", tone: "positive" as const };
  if (state === "excluded") return { label: "已排除", tone: "danger" as const };
  if (state === "reviewed") return { label: "已查看", tone: "neutral" as const };
  return { label: "未查看", tone: "warning" as const };
}

function eventDuration(item: Bookmark) {
  const durationMs = item.attributes.hikvision?.event_duration_ms;
  if (durationMs === null || durationMs === undefined) return "时长未知";
  if (durationMs < 1_000) return `${durationMs} 毫秒`;
  const seconds = Math.round(durationMs / 100) / 10;
  return `${seconds.toLocaleString("zh-CN")} 秒`;
}

function EventCard({ item, cameraName, preview, animation, onHover, onReview, onCandidate }: {
  item: Bookmark;
  cameraName: string;
  preview?: EventPreview;
  animation?: EventAnimation;
  onHover: () => void;
  onReview: (state: ReviewState) => void;
  onCandidate: () => void;
}) {
  const [hovering, setHovering] = useState(false);
  const evidence = item.attributes.hikvision;
  const image = hovering && animation?.status === "ready" ? animation : preview;
  const review = item.review_state ?? "unreviewed";
  const reviewLabel = reviewPresentation(review);
  return <article className={`${card} overflow-hidden ${review === "candidate" ? "ring-2 ring-emerald-500" : review === "excluded" ? "opacity-70" : ""}`}>
    <div className="relative aspect-video bg-[#142e29]" onMouseEnter={() => { setHovering(true); onHover(); }} onMouseLeave={() => setHovering(false)}>
      {image?.status === "ready" && image.content_url ? <img src={`${image.content_url}?v=${encodeURIComponent(image.job_id)}`} className="h-full w-full object-cover" alt={`${cameraName}事件预览`} /> : <div className="grid h-full place-items-center text-emerald-100/70"><Spinner label={hovering ? "生成 3 秒悬停预览" : "自动读取事件画面"} /></div>}
      <span className="absolute left-3 top-3"><Badge tone={reviewLabel.tone}>{reviewLabel.label}</Badge></span>
      <span className="absolute bottom-3 right-3 rounded-md bg-black/65 px-2 py-1 font-mono text-xs text-white">{eventDuration(item)}</span>
    </div>
    <div className="p-5"><Badge>{eventPresentation(evidence?.canonical_event_type || item.event_type)}</Badge><h3 className="mt-3 font-bold">{cameraName}</h3><p className="mt-1 text-sm text-slate-600">NVR 事件时间 {formatDateTime(item.start_at)}</p><p className="mt-3 text-xs leading-5 text-slate-500">来源：NVR 历史事件日志。摄像机画面里的 OSD 水印由摄像机自身时钟生成，可能与 NVR 事件时间不同。</p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        {review === "unreviewed" ? <Button onClick={() => onReview("reviewed")}>标为已看</Button> : <Button onClick={() => onReview("unreviewed")}>恢复未查看</Button>}
        {review === "excluded" ? <Button onClick={() => onReview("reviewed")}>移回结果</Button> : <Button variant="danger" onClick={() => onReview("excluded")}>排除</Button>}
        <Button className="col-span-2" variant="primary" disabled={review === "candidate" || !item.search_job_id} onClick={onCandidate}>{review === "candidate" ? "已加入候选" : "加入候选并生成视频"}</Button>
      </div>
    </div>
  </article>;
}
