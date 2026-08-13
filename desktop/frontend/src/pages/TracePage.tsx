import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, patch, post } from "../api";
import { CameraSnapshot } from "../CameraSnapshot";
import { useLoad } from "../hooks";
import {
  dateToLocalInput,
  eventDefinitions,
  eventPresentation,
  formatDateTime,
  formatDuration,
  lastNightWindow,
  localInputToRfc3339,
  shiftWindow,
  timeWindowLabel,
  type TimeWindow,
} from "../lib";
import type { View, NoticeSetter } from "../App";
import type {
  AppSettings,
  Bookmark,
  Channel,
  EventAnimation,
  EventAudit,
  EventPreview,
  Nvr,
  ReviewFilter,
  ReviewState,
  SearchPreset,
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

function inputWindow(from: string, to: string): TimeWindow {
  return { from: new Date(from), to: new Date(to) };
}

function sameScope(session: TraceSession | null, channelIds: string[], eventTypes: string[]) {
  if (!session) return false;
  const normalize = (values: string[]) => [...values].sort().join("|");
  return normalize(session.channel_ids) === normalize(channelIds)
    && normalize(session.event_types) === normalize(eventTypes);
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
  const sessions = useLoad(() => api<TraceSession[]>("/trace-sessions?limit=20"));
  const defaultWindow = useMemo(() => lastNightWindow(new Date()), []);
  const [channelsByNvr, setChannelsByNvr] = useState<Record<string, Channel[]>>({});
  const [auditsByNvr, setAuditsByNvr] = useState<Record<string, EventAudit>>({});
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [presetId, setPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const [from, setFrom] = useState(dateToLocalInput(defaultWindow.from));
  const [to, setTo] = useState(dateToLocalInput(defaultWindow.to));
  const [activeSession, setActiveSession] = useState<TraceSession | null>(null);
  const [results, setResults] = useState<TraceSessionResults | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("active");
  const [page, setPage] = useState(0);
  const [focusBucket, setFocusBucket] = useState<string | null>(null);
  const [historyRestored, setHistoryRestored] = useState(false);
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
    const window = lastNightWindow(new Date(), settings.data.night_start_hour, settings.data.night_end_hour);
    setFrom(dateToLocalInput(window.from));
    setTo(dateToLocalInput(window.to));
  }, [settings.data, timeTouched, activeSession]);

  useEffect(() => {
    if (historyRestored || sessions.loading || !sessions.data) return;
    setHistoryRestored(true);
    const latest = sessions.data[0];
    if (latest) void restoreSession(latest);
  }, [sessions.data, sessions.loading, historyRestored]); // eslint-disable-line react-hooks/exhaustive-deps

  const channels = useMemo(() => Object.values(channelsByNvr).flat(), [channelsByNvr]);
  const eligibleChannelIds = useMemo(() => new Set(channels.filter((channel) => {
    if (!eventTypes.length) return true;
    const audit = auditsByNvr[channel.nvr_id];
    if (!audit) return true;
    return eventTypes.some((eventType) => audit.rules.some((rule) =>
      rule.channel_external_id === channel.external_channel_id
      && rule.event_type === eventType
      && rule.state === "supported",
    ));
  }).map((channel) => channel.id)), [channels, auditsByNvr, eventTypes]);

  useEffect(() => {
    setSelectedChannels((current) => current.filter((channelId) => eligibleChannelIds.has(channelId)));
  }, [eligibleChannelIds]);
  const working = activeSession?.iterations.some((iteration) =>
    iteration.jobs.some((job) => ["queued", "running"].includes(job.state)),
  ) ?? false;

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
    nextPage = page,
    nextFilter = reviewFilter,
    bucket = focusBucket,
  ) {
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE), offset: String(nextPage * PAGE_SIZE), review_state: nextFilter,
    });
    if (bucket) {
      const bucketStart = new Date(bucket);
      query.set("from", bucketStart.toISOString());
      query.set("to", new Date(bucketStart.getTime() + 60 * 60 * 1000).toISOString());
    }
    const value = await api<TraceSessionResults>(`/trace-sessions/${sessionId}/results?${query}`);
    setResults(value);
    setPage(nextPage);
  }

  async function restoreSession(session: TraceSession) {
    setError(null);
    setActiveSession(session);
    setSelectedChannels(session.channel_ids);
    setEventTypes(session.event_types.filter((value) => eventDefinitions.some((item) => item.id === value)));
    setPresetId(session.preset_id ?? "");
    const latestIteration = [...session.iterations]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
    if (latestIteration) {
      setFrom(dateToLocalInput(new Date(latestIteration.from)));
      setTo(dateToLocalInput(new Date(latestIteration.to)));
      setTimeTouched(true);
    }
    setReviewFilter("active");
    setFocusBucket(null);
    await loadResults(session.id, 0, "active", null);
  }

  useEffect(() => {
    if (!activeSession || !working) return;
    const timer = window.setTimeout(async () => {
      try {
        const refreshed = await api<TraceSession>(`/trace-sessions/${activeSession.id}`);
        setActiveSession(refreshed);
        await loadResults(refreshed.id);
        if (!refreshed.iterations.some((iteration) => iteration.jobs.some((job) => ["queued", "running"].includes(job.state)))) {
          await sessions.refresh();
        }
      } catch (caught) {
        setError(caught as ApiError);
      }
    }, 800);
    return () => window.clearTimeout(timer);
  }, [activeSession, working, page, reviewFilter, focusBucket]); // eslint-disable-line react-hooks/exhaustive-deps

  async function ensureSession() {
    if (sameScope(activeSession, selectedChannels, eventTypes)) return activeSession as TraceSession;
    return post<TraceSession>("/trace-sessions", {
      channel_ids: selectedChannels,
      event_types: eventTypes,
      preset_id: presetId || null,
    });
  }

  async function executeWindows(windows: { window: TimeWindow; label: string }[]) {
    if (!selectedChannels.length) {
      setNotice({ tone: "error", text: "请至少选择一个摄像机画面。" });
      return;
    }
    if (windows.some(({ window }) => Number.isNaN(window.from.getTime()) || Number.isNaN(window.to.getTime()) || window.to <= window.from)) {
      setNotice({ tone: "error", text: "请选择有效的开始和结束时间。" });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let session = await ensureSession();
      for (const item of windows) {
        session = await post<TraceSession>(`/trace-sessions/${session.id}/iterations`, {
          from: item.window.from.toISOString(),
          to: item.window.to.toISOString(),
          label: item.label,
        });
      }
      setActiveSession(session);
      setFocusBucket(null);
      setReviewFilter("active");
      await loadResults(session.id, 0, "active", null);
      await sessions.refresh();
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setBusy(false);
    }
  }

  function search(event: FormEvent) {
    event.preventDefault();
    const window = inputWindow(from, to);
    void executeWindows([{ window, label: `自定义 · ${timeWindowLabel(window)}` }]);
  }

  function setQuickWindow(window: TimeWindow) {
    setFrom(dateToLocalInput(window.from));
    setTo(dateToLocalInput(window.to));
    setTimeTouched(true);
  }

  async function queryAdjacent(days: number) {
    const shifted = shiftWindow(inputWindow(from, to), days);
    setQuickWindow(shifted);
    await executeWindows([{ window: shifted, label: `${days < 0 ? "前一晚" : "后一晚"} · ${timeWindowLabel(shifted)}` }]);
  }

  async function queryThreeNights() {
    const center = inputWindow(from, to);
    const previous = shiftWindow(center, -1);
    const next = shiftWindow(center, 1);
    await executeWindows([
      { window: previous, label: `扩展前一晚 · ${timeWindowLabel(previous)}` },
      { window: center, label: `当前夜晚 · ${timeWindowLabel(center)}` },
      { window: next, label: `扩展后一晚 · ${timeWindowLabel(next)}` },
    ]);
  }

  function applyPreset(id: string) {
    setPresetId(id);
    const preset = presets.data?.find((item) => item.id === id);
    if (!preset) return;
    setSelectedChannels(preset.channel_ids);
    setEventTypes(preset.event_types.filter((value) => eventDefinitions.some((item) => item.id === value)));
  }

  async function savePreset() {
    if (!presetName.trim() || !selectedChannels.length) return;
    try {
      const saved = await post<SearchPreset>("/search-presets", {
        name: presetName.trim(), channel_ids: selectedChannels, event_types: eventTypes,
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

  async function changeReview(item: Bookmark, state: ReviewState) {
    if (!activeSession) return;
    try {
      await patch(`/trace-sessions/${activeSession.id}/events/${item.id}`, { state });
      await loadResults(activeSession.id);
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
        window_override: { pre_roll_ms: 5_000, post_roll_ms: 10_000, max_duration_ms: 30_000 },
        audio_policy: "prefer",
      });
      await patch(`/trace-sessions/${activeSession.id}/events/${item.id}`, { state: "candidate" });
      await loadResults(activeSession.id);
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
    } catch { /* result cards remain usable if the NVR cannot render a preview */ }
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
    } catch { /* static preview remains available */ }
  }

  useEffect(() => {
    for (const item of results?.items ?? []) void ensurePreview(item);
  }, [results?.items]); // eslint-disable-line react-hooks/exhaustive-deps

  async function chooseReviewFilter(next: ReviewFilter) {
    if (!activeSession) return;
    setReviewFilter(next);
    try { await loadResults(activeSession.id, 0, next, focusBucket); }
    catch (caught) { setError(caught as ApiError); }
  }

  async function chooseDensityBucket(bucket: string | null) {
    if (!activeSession) return;
    setFocusBucket(bucket);
    try { await loadResults(activeSession.id, 0, reviewFilter, bucket); }
    catch (caught) { setError(caught as ApiError); }
  }

  function startNewSearch() {
    setActiveSession(null);
    setResults(null);
    setReviewFilter("active");
    setFocusBucket(null);
    const window = lastNightWindow(
      new Date(), settings.data?.night_start_hour ?? 18, settings.data?.night_end_hour ?? 6,
    );
    setQuickWindow(window);
  }

  if (!nvrs.loading && nvrs.data?.length === 0) {
    return <><Header eyebrow="EVENT → TRACE" title="从事件找到关键录像" description="先添加 NVR，再用时间、摄像机画面和事件类型逐步逼近目标录像。" /><Empty title="还没有可检索的 NVR" description="请先在设备中心添加设备。" action={<Button variant="primary" onClick={() => navigate("devices")}>前往设备中心</Button>} /></>;
  }

  const groupedResults = Object.entries(
    (results?.items ?? []).reduce<Record<string, Bookmark[]>>((groups, item) => {
      const key = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date(item.start_at));
      (groups[key] ??= []).push(item);
      return groups;
    }, {}),
  );
  const maxDensity = Math.max(1, ...(results?.density ?? []).map((item) => item.count));

  return <>
    <Header
      eyebrow="EVENT → TRACE"
      title="从事件找到关键录像"
      description="先固定摄像机和事件类型，再用前一晚、后一晚和事件密度反复逼近；每次结果自动累积、去重并保留筛选进度。"
      action={<Button onClick={() => navigate("exports")}>查看候选与导出</Button>}
    />
    <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-5 py-3 text-sm leading-6 text-amber-950"><strong>证据边界：</strong>TraceCue 读取 NVR 已保存的事件日志，并按事件时间定位连续录像。返回 0 个事件不等于“没有人经过”；请尝试前后夜，或检查该摄像机是否支持且启用了对应事件。</div>
    <Problem error={error ?? nvrs.error ?? presets.error ?? settings.error ?? sessions.error} />

    <section className={`${card} mb-5 flex flex-wrap items-end gap-3 p-4`}>
      <label className="min-w-72 flex-1 text-xs font-semibold text-slate-600">继续最近搜索
        <select className={`${field} mt-1`} value={activeSession?.id ?? ""} onChange={(event) => {
          const session = sessions.data?.find((item) => item.id === event.target.value);
          if (session) void restoreSession(session);
        }}>
          <option value="">未选择历史搜索</option>
          {sessions.data?.map((session) => <option key={session.id} value={session.id}>{formatDateTime(session.updated_at)} · {session.result_count} 个事件 · {session.iterations.length} 次检索</option>)}
        </select>
      </label>
      <Button onClick={startNewSearch}>新建搜索</Button>
    </section>

    <form onSubmit={search} className={`${card} p-5 sm:p-7`}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-56 flex-1 text-sm font-semibold text-slate-700">开始时间<input required type="datetime-local" className={`${field} mt-2`} value={from} onChange={(event) => { setFrom(event.target.value); setTimeTouched(true); }} /></label>
        <label className="min-w-56 flex-1 text-sm font-semibold text-slate-700">结束时间<input required type="datetime-local" className={`${field} mt-2`} value={to} onChange={(event) => { setTo(event.target.value); setTimeTouched(true); }} /></label>
        <Button type="button" onClick={() => setQuickWindow(lastNightWindow(new Date(), settings.data?.night_start_hour ?? 18, settings.data?.night_end_hour ?? 6))}>填入昨晚</Button>
      </div>

      <fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">先选择事件类型</legend><p className="mb-3 text-xs leading-5 text-slate-500">选择 Smart 事件后，下方只显示已由设备接口证明具备该能力的摄像机。不选择时查询四类已识别事件；连续录像不会作为事件结果。</p><div className="grid gap-3 md:grid-cols-2">
        {(["ordinary", "smart"] as const).map((category) => <div key={category} className={`rounded-xl border p-4 ${category === "smart" ? "border-amber-200 bg-amber-50/60" : "border-slate-200 bg-slate-50"}`}><strong className="mb-3 block text-sm">{category === "smart" ? "Smart 事件 · 设备相关" : "普通事件 · 基础能力"}</strong><div className="flex flex-wrap gap-2">{eventDefinitions.filter((item) => item.category === category).map((item) => <label key={item.id} className={`cursor-pointer rounded-full border px-3 py-2 text-xs font-semibold ${eventTypes.includes(item.id) ? "border-emerald-500 bg-emerald-100 text-emerald-900" : "border-slate-200 bg-white text-slate-600"}`}><input className="sr-only" type="checkbox" checked={eventTypes.includes(item.id)} onChange={() => setEventTypes((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.label} · {capableCameraCount(item.id)} 台</label>)}</div></div>)}
      </div></fieldset>

      <fieldset className="mt-6"><legend className="mb-3 text-sm font-semibold text-slate-700">再选择摄像机画面</legend><div className="space-y-5">
        {nvrs.data?.map((nvr) => { const visibleChannels = (channelsByNvr[nvr.id] ?? []).filter((channel) => eligibleChannelIds.has(channel.id)); return <div key={nvr.id}><h3 className="mb-2 text-sm font-bold">{nvr.name} <span className="font-normal text-slate-500">· {visibleChannels.length} 台可用</span></h3>{visibleChannels.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visibleChannels.map((channel) => <label key={channel.id} className={`cursor-pointer overflow-hidden rounded-2xl border bg-white transition ${selectedChannels.includes(channel.id) ? "border-emerald-500 ring-2 ring-emerald-200" : "border-slate-200"}`}><div className="relative"><CameraSnapshot channel={channel} /><input className="absolute left-3 top-3 h-5 w-5 accent-emerald-700" type="checkbox" checked={selectedChannels.includes(channel.id)} onChange={() => setSelectedChannels((current) => current.includes(channel.id) ? current.filter((id) => id !== channel.id) : [...current, channel.id])} /></div><div className="p-3"><strong className="block text-sm">{channel.alias || channel.device_name || "未命名摄像机"}</strong><small className="text-slate-500">{channel.online ? "在线" : "状态未知 / 离线"} · 通道 {channel.external_channel_id}</small></div></label>)}
        </div> : <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">这台 NVR 没有摄像机具备当前所选事件能力。可到设备中心重新扫描事件配置。</div>}</div>; })}
      </div></fieldset>

      <div className="mt-6 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-5">
        <label className="min-w-56 text-xs font-semibold text-slate-600">加载常用筛选<select className={`${field} mt-1`} value={presetId} onChange={(event) => applyPreset(event.target.value)}><option value="">未加载</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        {presetId && <Button type="button" variant="ghost" onClick={deletePreset}>删除此筛选</Button>}
        <label className="min-w-56 text-xs font-semibold text-slate-600">保存当前筛选<input className={`${field} mt-1`} value={presetName} onChange={(event) => setPresetName(event.target.value)} placeholder="例如：夜间门口行人" /></label>
        <Button type="button" onClick={savePreset} disabled={!presetName.trim() || !selectedChannels.length}>保存筛选</Button>
        <Button className="ml-auto" variant="primary" type="submit" disabled={busy || !selectedChannels.length}>{busy ? "提交中…" : activeSession && sameScope(activeSession, selectedChannels, eventTypes) ? "检索此时间段" : "开始新的 Trace"}</Button>
      </div>
    </form>

    {activeSession && <section className={`${card} mt-5 p-5`}>
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">TRACE SESSION</p><h2 className="mt-1 text-xl font-bold">同一目标，逐晚逼近</h2></div><div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => void queryAdjacent(-1)}>查询前一晚</Button><Button disabled={busy} onClick={() => void queryAdjacent(1)}>查询后一晚</Button><Button disabled={busy} variant="primary" onClick={() => void queryThreeNights()}>扩展为前后 3 晚</Button></div></div>
      <div className="mt-4 flex flex-wrap gap-2">{activeSession.channel_ids.map((channelId) => <Badge key={channelId}>{cameraName(channelId, channelId)}</Badge>)}{activeSession.event_types.length ? activeSession.event_types.map((type) => <Badge key={type}>{eventPresentation(type)}</Badge>) : <Badge>全部事件类型</Badge>}</div>
      <div className="mt-5 flex gap-3 overflow-x-auto pb-2">{activeSession.iterations.length === 0 ? <span className="text-sm text-slate-500">尚未提交时间窗口。</span> : activeSession.iterations.map((iteration) => <article key={iteration.id} className="min-w-72 rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-2"><strong className="text-sm">{iteration.label}</strong><Badge tone={iteration.state === "succeeded" ? "positive" : iteration.state === "running" ? "warning" : "danger"}>{iteration.state === "running" ? "检索中" : iteration.state === "succeeded" ? "完成" : iteration.state === "partial" ? "部分完成" : "失败"}</Badge></div><p className="mt-2 text-xs leading-5 text-slate-600">{exactWindow(iteration.from, iteration.to)}</p><p className="mt-2 text-sm font-semibold">{iteration.result_count} 个事件</p>{iteration.jobs.flatMap((job) => job.error ? [<p key={job.id} className="mt-2 text-xs text-red-700">{job.error.code} · {job.error.message}</p>] : [])}</article>)}</div>
      {working && <div className="mt-3"><Spinner label="正在从 NVR 读取新时间窗口；已有结果仍可继续筛选" /></div>}
    </section>}

    {activeSession && results && <section className="mt-8">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="font-mono text-[10px] tracking-[.18em] text-emerald-700">CUMULATIVE RESULTS</p><h2 className="mt-1 text-2xl font-bold">累计去重 {activeSession.result_count} 个事件</h2><p className="mt-1 text-sm text-slate-500">当前视图 {results.total} 个；跨时间窗口遇到同一事件只显示一次。</p></div><div className="flex items-center gap-2"><Button disabled={page === 0} onClick={() => void loadResults(activeSession.id, page - 1)}>上一页</Button><Badge>第 {page + 1} 页</Badge><Button disabled={!results.has_more} onClick={() => void loadResults(activeSession.id, page + 1)}>下一页</Button></div></div>

      <div className={`${card} mb-5 p-5`}>
        <div className="flex flex-wrap gap-2">{reviewFilters.map((filter) => {
          const count = filter.id === "all" ? Object.values(results.counts).reduce((sum, value) => sum + value, 0)
            : filter.id === "active" ? results.counts.unreviewed + results.counts.reviewed + results.counts.candidate
              : results.counts[filter.id];
          return <button type="button" key={filter.id} onClick={() => void chooseReviewFilter(filter.id)} className={`rounded-full border px-3 py-2 text-xs font-semibold ${reviewFilter === filter.id ? "border-emerald-600 bg-emerald-700 text-white" : "border-slate-200 bg-white text-slate-600"}`}>{filter.label} {count}</button>;
        })}</div>
        {results.density.length > 0 && <div className="mt-5"><div className="mb-2 flex items-center justify-between"><strong className="text-sm">事件密度 · 点击小时快速聚焦</strong>{focusBucket && <button type="button" className="text-xs font-semibold text-emerald-700" onClick={() => void chooseDensityBucket(null)}>清除小时聚焦</button>}</div><div className="flex min-h-24 items-end gap-1 overflow-x-auto rounded-xl bg-slate-50 p-3">{results.density.map((bucket) => <button type="button" key={bucket.start_at} title={`${formatDateTime(bucket.start_at)} · ${bucket.count} 个事件`} aria-label={`${formatDateTime(bucket.start_at)}，${bucket.count} 个事件`} onClick={() => void chooseDensityBucket(bucket.start_at)} className={`min-w-7 rounded-t transition ${focusBucket === bucket.start_at ? "bg-amber-500" : "bg-emerald-600 hover:bg-emerald-500"}`} style={{ height: `${Math.max(12, Math.round(bucket.count / maxDensity * 72))}px` }}><span className="sr-only">{bucket.count}</span></button>)}</div></div>}
      </div>

      {results.items.length === 0 ? <Empty title={focusBucket ? "这个小时没有匹配事件" : "这个时间范围还没有发现目标"} description="保持摄像机与事件类型不变，直接查询前一晚、后一晚，或一次扩展前后 3 晚。" action={<div className="flex flex-wrap justify-center gap-2"><Button onClick={() => void queryAdjacent(-1)}>查前一晚</Button><Button onClick={() => void queryAdjacent(1)}>查后一晚</Button><Button variant="primary" onClick={() => void queryThreeNights()}>查前后 3 晚</Button></div>} /> : groupedResults.map(([date, items]) => <div key={date} className="mb-7"><h3 className="mb-3 text-lg font-bold">{date}</h3><div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{items.map((item) => <EventCard key={item.id} item={item} cameraName={cameraName(item.media_channel_id, item.media_channel_label || item.source_channel.label)} preview={previews[item.id]} animation={animations[item.id]} onHover={() => ensureAnimation(item)} onReview={(state) => changeReview(item, state)} onCandidate={() => createCandidate(item)} />)}</div></div>)}
    </section>}
  </>;
}

function reviewPresentation(state: ReviewState) {
  if (state === "candidate") return { label: "已加入候选", tone: "positive" as const };
  if (state === "excluded") return { label: "已排除", tone: "danger" as const };
  if (state === "reviewed") return { label: "已查看", tone: "neutral" as const };
  return { label: "未查看", tone: "warning" as const };
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
      <span className="absolute bottom-3 right-3 rounded-md bg-black/65 px-2 py-1 font-mono text-xs text-white">{formatDuration(item.start_at, item.end_at)}</span>
    </div>
    <div className="p-5"><Badge>{eventPresentation(evidence?.canonical_event_type || item.event_type)}</Badge><h3 className="mt-3 font-bold">{cameraName}</h3><p className="mt-1 text-sm text-slate-600">事件发生于 {formatDateTime(item.start_at)}</p><p className="mt-3 text-xs leading-5 text-slate-500">来源：NVR 历史事件日志；视频由该时间点映射到 NVR 连续录像。移入画面可播放缓存的 3 秒预览。</p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        {review === "unreviewed" ? <Button onClick={() => onReview("reviewed")}>标为已看</Button> : <Button onClick={() => onReview("unreviewed")}>恢复未查看</Button>}
        {review === "excluded" ? <Button onClick={() => onReview("reviewed")}>移回结果</Button> : <Button variant="danger" onClick={() => onReview("excluded")}>排除</Button>}
        <Button className="col-span-2" variant="primary" disabled={review === "candidate" || !item.search_job_id} onClick={onCandidate}>{review === "candidate" ? "已加入候选" : "加入候选并生成视频"}</Button>
      </div>
    </div>
  </article>;
}
