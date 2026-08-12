import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api, patch, post, put } from "./api";
import { comparisonMetrics, formatDateTime, formatDuration, localInputToRfc3339, sourcePresentation } from "./lib";
import type { Bookmark, Channel, Clip, Job, Nvr, SourceChannel } from "./types";

type View = "find" | "review" | "clips" | "devices" | "sources" | "comparison" | "settings";

const navigation: { id: View; label: string; eyebrow: string }[] = [
  { id: "find", label: "查找录像", eyebrow: "NVR" },
  { id: "review", label: "值得查看", eyebrow: "时间轴" },
  { id: "clips", label: "已导出片段", eyebrow: "媒体" },
  { id: "sources", label: "来源与映射", eyebrow: "配置" },
  { id: "comparison", label: "对照评估", eyebrow: "验证" },
  { id: "devices", label: "设备", eyebrow: "NVR" },
  { id: "settings", label: "诊断与设置", eyebrow: "本机" },
];

function useLoad<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
      setError(null);
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }, dependencies); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void refresh(), [refresh]);
  return { data, error, loading, refresh };
}

export default function App() {
  const initial = (window.location.hash.slice(1) as View) || "find";
  const [view, setView] = useState<View>(navigation.some((item) => item.id === initial) ? initial : "find");
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const navigate = (next: View) => {
    setView(next);
    window.location.hash = next;
    setNotice(null);
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <div><strong>TraceCue</strong><small>录像线索台</small></div>
        </div>
        <nav aria-label="主导航">
          {navigation.map((item) => (
            <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => navigate(item.id)}>
              <span>{item.label}</span><small>{item.eyebrow}</small>
            </button>
          ))}
        </nav>
        <div className="local-badge"><span /> 仅本机访问 · 127.0.0.1</div>
      </aside>
      <main>
        {notice && <div className={`toast ${notice.tone}`} role="status">{notice.text}</div>}
        {view === "find" && <FindView setNotice={setNotice} navigate={navigate} />}
        {view === "review" && <ReviewView setNotice={setNotice} />}
        {view === "clips" && <ClipsView setNotice={setNotice} />}
        {view === "devices" && <DevicesView setNotice={setNotice} />}
        {view === "sources" && <SourcesView setNotice={setNotice} />}
        {view === "comparison" && <ComparisonView />}
        {view === "settings" && <SettingsView setNotice={setNotice} />}
      </main>
    </div>
  );
}

function Header({ kicker, title, subtitle, action }: { kicker: string; title: string; subtitle: string; action?: ReactNode }) {
  return <header className="page-header"><div><p>{kicker}</p><h1>{title}</h1><span>{subtitle}</span></div>{action}</header>;
}

function Empty({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return <div className="empty"><div className="empty-rings" aria-hidden="true"><i /><i /><i /></div><h3>{title}</h3><p>{text}</p>{action}</div>;
}

function Problem({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <div className="problem" role="alert"><strong>{error.code}</strong><span>{error.message}</span><small>{error.requestId}</small></div>;
}

function FindView({ setNotice, navigate }: { setNotice: NoticeSetter; navigate: (view: View) => void }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const [nvrId, setNvrId] = useState("");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const today = new Date();
  const earlier = new Date(today.getTime() - 60 * 60 * 1000);
  const [from, setFrom] = useState(earlier.toISOString().slice(0, 16));
  const [to, setTo] = useState(today.toISOString().slice(0, 16));
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!nvrId) { setChannels([]); return; }
    api<Channel[]>(`/nvrs/${nvrId}/channels`).then(setChannels).catch(() => setChannels([]));
  }, [nvrId]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.state)) return;
    const timer = window.setInterval(async () => setJob(await api<Job>(`/jobs/${job.id}`)), 700);
    return () => window.clearInterval(timer);
  }, [job]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await post<Job>("/search-jobs", {
        nvr_id: nvrId,
        channel_ids: selected,
        from: localInputToRfc3339(from),
        to: localInputToRfc3339(to),
        source_modes: ["record_classification"],
      });
      setJob(created);
    } catch (caught) {
      setNotice({ tone: "error", text: (caught as Error).message });
    } finally { setBusy(false); }
  }

  return <>
    <Header kicker="NVR FOUNDATION" title="查找录像" subtitle="按设备、通道和时间窗口索引 NVR 已有录像。" />
    <div className="truth-note"><strong>来源说明</strong><span>NVR 候选来自设备自己的录像/事件元数据，可能包含灯光、反射或画面外活动造成的误报；这里不会标为“高置信”。</span></div>
    <section className="card search-card">
      {nvrs.data?.length === 0 ? <Empty title="先添加一台 NVR" text="完成只读连接、时钟和通道检查后，才能检索录像。" action={<button className="primary" onClick={() => navigate("devices")}>前往添加设备</button>} /> :
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>录像机<select required value={nvrId} onChange={(e) => { setNvrId(e.target.value); setSelected([]); }}><option value="">请选择</option>{nvrs.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>开始时间<input required type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label>结束时间<input required type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        </div>
        <fieldset><legend>通道</legend><div className="choice-grid">{channels.map((channel) => <label key={channel.id} className={selected.includes(channel.id) ? "choice selected" : "choice"}><input type="checkbox" checked={selected.includes(channel.id)} onChange={() => setSelected((current) => current.includes(channel.id) ? current.filter((id) => id !== channel.id) : [...current, channel.id])} /><span>{channel.alias || channel.device_name}<small>{channel.online ? "在线" : "离线"} · track {channel.primary_track_id || "未知"}</small></span></label>)}</div></fieldset>
        <button className="primary" disabled={busy || !nvrId || selected.length === 0}>{busy ? "正在提交…" : "开始检索"}</button>
      </form>}
      <Problem error={nvrs.error} />
    </section>
    {job && <JobPanel job={job} onDone={() => navigate("review")} />}
  </>;
}

function JobPanel({ job, onDone }: { job: Job; onDone: () => void }) {
  return <section className="card job-panel"><div><p>后台作业</p><h3>{job.state === "succeeded" ? "检索完成" : job.state === "failed" ? "检索失败" : "正在从 NVR 建立索引"}</h3></div><div className="progress"><i style={{ width: `${Math.max(4, job.progress * 100)}%` }} /></div>{job.error && <div className="problem"><strong>{job.error.code}</strong><span>{job.error.message}</span></div>}{job.state === "succeeded" && <button className="primary" onClick={onDone}>查看候选</button>}</section>;
}

function ReviewView({ setNotice }: { setNotice: NoticeSetter }) {
  const result = useLoad(() => api<{ items: Bookmark[]; next_cursor: string | null }>("/bookmarks?limit=100"));
  const [filter, setFilter] = useState<"worth" | "all" | "nvr">("worth");
  const [generating, setGenerating] = useState<string | null>(null);
  const items = useMemo(() => (result.data?.items ?? []).filter((item) => {
    if (filter === "worth") return item.quality.gate === "pass" && item.source.kind !== "nvr";
    if (filter === "nvr") return item.source.kind === "nvr";
    return true;
  }), [result.data, filter]);

  async function generate(item: Bookmark) {
    setGenerating(item.id);
    try {
      const clip = await post<Clip>("/clips", { bookmark_id: item.id, audio_policy: "prefer" });
      setNotice({ tone: "success", text: `片段作业已创建：${clip.id}` });
    } catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
    finally { setGenerating(null); }
  }

  return <>
    <Header kicker="REVIEW QUEUE" title="值得查看" subtitle="质量状态、来源和时钟修正始终可见。" action={<div className="segmented"><button className={filter === "worth" ? "active" : ""} onClick={() => setFilter("worth")}>高置信</button><button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部</button><button className={filter === "nvr" ? "active" : ""} onClick={() => setFilter("nvr")}>NVR 候选</button></div>} />
    <Problem error={result.error} />
    {items.length === 0 && !result.loading ? <Empty title={filter === "worth" ? "还没有高置信书签" : "没有匹配候选"} text={filter === "worth" ? "导入并映射通过质量门的 timeline.v1，或切换到“全部”查看 NVR 候选。" : "调整检索窗口后重试。"} /> : <div className="timeline-list">{items.map((item) => <BookmarkRow key={item.id} item={item} action={<button disabled={generating === item.id} onClick={() => generate(item)}>{generating === item.id ? "提交中…" : "生成片段"}</button>} />)}</div>}
  </>;
}

function BookmarkRow({ item, action }: { item: Bookmark; action?: ReactNode }) {
  const source = sourcePresentation(item);
  return <article className="bookmark"><div className="time"><strong>{formatDateTime(item.start_at).slice(-8)}</strong><span>{formatDuration(item.start_at, item.end_at)}</span></div><div className="bookmark-body"><div><span className={`pill ${source.tone}`}>{source.label}</span><span className="event-type">{item.event_type}</span></div><h3>{item.source_channel.label}</h3><p>{source.explanation} · {item.media_channel_label || "尚未映射摄像机"}</p>{item.clock_correction_ms !== 0 && <small>时钟修正 {item.clock_correction_ms > 0 ? "+" : ""}{item.clock_correction_ms} ms</small>}</div><div className="bookmark-action">{action}</div></article>;
}

function ClipsView({ setNotice }: { setNotice: NoticeSetter }) {
  const clips = useLoad(() => api<Clip[]>("/clips"));
  async function remove(id: string) {
    if (!window.confirm("删除这个本地派生片段？NVR 原录像不会受影响。")) return;
    try { await api(`/clips/${id}`, { method: "DELETE" }); await clips.refresh(); setNotice({ tone: "success", text: "本地片段已删除，NVR 原录像未更改。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
  }
  return <><Header kicker="DERIVED MEDIA" title="已导出片段" subtitle="片段是可删除的派生文件，NVR 始终保留权威原录像。" /><Problem error={clips.error} />{clips.data?.length ? <div className="clip-grid">{clips.data.map((clip) => <article className="clip-card" key={clip.id}>{clip.content_url ? <video controls preload="metadata" src={clip.content_url} /> : <div className="clip-placeholder"><span>{clip.status}</span></div>}<div><span className={`pill ${clip.status === "ready" ? "positive" : clip.status === "failed" ? "danger" : "warning"}`}>{clip.status}</span><h3>{formatDateTime(clip.requested_window.start_at)}</h3><p>{clip.video_codec || "等待媒体信息"}{clip.audio_codec ? ` · ${clip.audio_codec}` : ""}</p><button className="text-button danger-text" onClick={() => remove(clip.id)}>删除本地片段</button></div></article>)}</div> : <Empty title="还没有导出片段" text="从书签生成短片后，可在这里播放或另存。" />}</>;
}

function DevicesView({ setNotice }: { setNotice: NoticeSetter }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", host: "", username: "", password: "", http_port: 80, use_https: false, verify_tls: true });
  const [probe, setProbe] = useState<Record<string, unknown> | null>(null);

  async function check() {
    setBusy(true);
    try { setProbe(await post("/nvrs/probe", form)); setNotice({ tone: "success", text: "只读探测完成。请核对时钟与能力状态。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
    finally { setBusy(false); }
  }
  async function add(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    try { await post("/nvrs", form); setShowForm(false); setProbe(null); await nvrs.refresh(); setNotice({ tone: "success", text: "NVR 已添加，凭据保存在 Windows 受保护存储中。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
    finally { setBusy(false); }
  }
  return <><Header kicker="DEVICE EVIDENCE" title="设备" subtitle="兼容性按型号、固件和端点证据记录。" action={<button className="primary" onClick={() => setShowForm((value) => !value)}>{showForm ? "取消" : "添加 NVR"}</button>} />
    {showForm && <section className="card"><form onSubmit={add}><div className="form-grid"><label>显示名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：前台录像机" /></label><label>NVR 地址<input required value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="192.0.2.10" /></label><label>HTTP(S) 端口<input type="number" min="1" max="65535" value={form.http_port} onChange={(e) => setForm({ ...form, http_port: Number(e.target.value) })} /></label><label>用户名<input required autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label><label>密码<input required type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label></div><div className="inline-checks"><label><input type="checkbox" checked={form.use_https} onChange={(e) => setForm({ ...form, use_https: e.target.checked, http_port: e.target.checked ? 443 : 80 })} /> 使用 HTTPS</label><label><input type="checkbox" checked={form.verify_tls} onChange={(e) => setForm({ ...form, verify_tls: e.target.checked })} /> 验证 TLS 证书</label></div><div className="button-row"><button type="button" onClick={check} disabled={busy}>只读探测</button><button className="primary" disabled={busy || !probe}>确认添加</button></div></form>{probe && <pre className="evidence">{JSON.stringify(probe, null, 2)}</pre>}</section>}
    <Problem error={nvrs.error} /><div className="device-grid">{nvrs.data?.map((nvr) => <DeviceCard key={nvr.id} nvr={nvr} setNotice={setNotice} />)}</div>{nvrs.data?.length === 0 && !showForm && <Empty title="还没有设备" text="添加 NVR 时会先执行只读身份、时钟和通道探测。" />}</>;
}

function DeviceCard({ nvr, setNotice }: { nvr: Nvr; setNotice: NoticeSetter }) {
  const channels = useLoad(() => api<Channel[]>(`/nvrs/${nvr.id}/channels`), [nvr.id]);
  async function rename(channel: Channel) {
    const alias = window.prompt("设置房间/通道别名", channel.alias || channel.device_name);
    if (alias === null) return;
    try { await patch(`/channels/${channel.id}`, { alias }); await channels.refresh(); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
  }
  return <section className="card device-card"><div className="device-head"><div><span className="status-dot" /><h3>{nvr.name}</h3></div><span>{nvr.use_https ? "HTTPS" : "HTTP"} · {nvr.host}:{nvr.http_port}</span></div><dl><div><dt>型号</dt><dd>{nvr.model || "未知"}</dd></div><div><dt>固件</dt><dd>{nvr.firmware || "未知"}</dd></div><div><dt>时钟偏差</dt><dd className={Math.abs(nvr.clock_skew_ms || 0) >= 30000 ? "danger-text" : ""}>{nvr.clock_skew_ms ?? "未知"} ms</dd></div></dl><div className="channel-list">{channels.data?.map((channel) => <button key={channel.id} onClick={() => rename(channel)}><span>{channel.alias || channel.device_name}</span><small>{channel.online ? "在线" : "离线"} · 编辑别名</small></button>)}</div></section>;
}

function SourcesView({ setNotice }: { setNotice: NoticeSetter }) {
  const sources = useLoad(() => api<SourceChannel[]>("/source-channels"));
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const [channels, setChannels] = useState<Channel[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<{ id: string; content_hash: string; status: string; diagnostics: Record<string, unknown> } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { Promise.all((nvrs.data ?? []).map((nvr) => api<Channel[]>(`/nvrs/${nvr.id}/channels`))).then((groups) => setChannels(groups.flat())); }, [nvrs.data]);

  async function inspect() {
    if (!file) return; setBusy(true);
    try {
      const response = await fetch("/api/v1/timeline-imports/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: await file.arrayBuffer() });
      if (!response.ok) { const body = await response.json(); throw new Error(body.error?.message || "导入检查失败"); }
      setInspection(await response.json());
    } catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
    finally { setBusy(false); }
  }
  async function commit() {
    if (!inspection) return; setBusy(true);
    try { await post(`/timeline-imports/${inspection.id}/commit`, { content_hash: inspection.content_hash }); await sources.refresh(); setNotice({ tone: "success", text: "timeline.v1 已幂等提交；未映射来源不能生成片段。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
    finally { setBusy(false); }
  }
  async function bind(source: SourceChannel, channelId: string) {
    const spaceName = window.prompt("业务空间名称", source.space_name || source.label);
    if (!spaceName) return;
    const correction = Number(window.prompt("时钟修正（毫秒，可为负数）", String(source.clock_correction_ms || 0)) || 0);
    try { await put(`/source-channels/${source.id}/binding`, { space_name: spaceName, nvr_channel_id: channelId, clock_correction_ms: correction }); await sources.refresh(); setNotice({ tone: "success", text: "映射与时钟修正已保存，原始来源时间保持不变。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
  }
  return <><Header kicker="TIMELINE.V1" title="来源与映射" subtitle="先检查，再提交；来源通道通过业务空间连接到稳定的 NVR 通道。" /><section className="card import-card"><div><h3>导入 timeline.v1</h3><p>文件上限 8 MiB。检查不会写入 Interval 表，提交按 source_id + interval.id 幂等。</p></div><input type="file" accept="application/json,.json" onChange={(e) => setFile(e.target.files?.[0] || null)} /><div className="button-row"><button disabled={!file || busy} onClick={inspect}>检查文件</button><button className="primary" disabled={!inspection || busy} onClick={commit}>提交导入</button></div>{inspection && <pre className="evidence">{JSON.stringify(inspection.diagnostics, null, 2)}</pre>}</section><Problem error={sources.error} /><div className="mapping-list">{sources.data?.map((source) => <article key={source.id}><div><span className={`pill ${source.space_id ? "positive" : "warning"}`}>{source.space_id ? "已映射" : "待映射"}</span><h3>{source.label}</h3><p>{source.external_source_id} · {source.kind}</p></div><div className="mapping-arrow">→</div><select value={source.nvr_channel_id || ""} onChange={(e) => e.target.value && bind(source, e.target.value)}><option value="">选择摄像机</option>{channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.alias || channel.device_name}</option>)}</select><small>{source.space_name || "无业务空间"}{source.clock_correction_ms ? ` · 修正 ${source.clock_correction_ms} ms` : ""}</small></article>)}</div></>;
}

function ComparisonView() {
  const result = useLoad(() => api<{ items: Bookmark[] }>("/bookmarks?limit=200"));
  const metrics = comparisonMetrics(result.data?.items ?? []);
  return <><Header kicker="VALIDATION, NOT MARKETING" title="对照评估" subtitle="审阅量变化必须与人工标注召回率一起解释。" /><div className="metric-grid"><Metric label="高置信书签" value={String(metrics.highConfidence)} note="质量门通过且非 NVR 来源" /><Metric label="NVR 候选" value={String(metrics.nvrCandidates)} note="相同导入/检索窗口内" /><Metric label="审阅量变化" value={metrics.reviewReduction === null ? "—" : `${Math.round(metrics.reviewReduction * 100)}%`} note="没有召回率时不能声称改进" /><Metric label="重要事件召回率" value="未标注" note="需要 golden dataset 人工标签" warning /></div><section className="card validation-note"><h3>为什么现在不能下结论</h3><p>减少书签数量也可能只是漏掉真实事件。只有给定同一窗口的人工重要事件标签、算法版本和时钟修正后，才能同时计算精度、召回率、审阅量与找片耗时。</p><span className="pill warning">canClaimImprovement: {String(metrics.canClaimImprovement)}</span></section></>;
}

function Metric({ label, value, note, warning }: { label: string; value: string; note: string; warning?: boolean }) {
  return <article className={`metric ${warning ? "metric-warning" : ""}`}><span>{label}</span><strong>{value}</strong><p>{note}</p></article>;
}

function SettingsView({ setNotice }: { setNotice: NoticeSetter }) {
  const status = useLoad(() => api<Record<string, any>>("/status"));
  const diagnostics = useLoad(() => api<Record<string, any>>("/diagnostics"));
  const settings = useLoad(() => api<Record<string, number>>("/settings"));
  const [draft, setDraft] = useState<Record<string, number>>({});
  useEffect(() => { if (settings.data) setDraft(settings.data); }, [settings.data]);
  async function save(event: FormEvent) {
    event.preventDefault();
    try { await patch("/settings", draft); await settings.refresh(); setNotice({ tone: "success", text: "本机设置已保存。" }); }
    catch (caught) { setNotice({ tone: "error", text: (caught as Error).message }); }
  }
  return <><Header kicker="LOCAL DIAGNOSTICS" title="诊断与设置" subtitle="不显示文件系统秘密、凭据或 RTSP 定位符。" /><div className="settings-grid"><section className="card"><h3>运行状态</h3><pre className="evidence">{JSON.stringify(status.data, null, 2)}</pre><h3>支持包脱敏预览</h3><p>下载前仍应人工复核；地址、凭据、RTSP locator、路径和原始上游响应已移除。</p><pre className="evidence">{JSON.stringify(diagnostics.data, null, 2)}</pre><a className="download-button" href="/api/v1/diagnostics/export" download>下载诊断 JSON</a></section><section className="card"><h3>片段与窗口</h3><form onSubmit={save}><label>片段配额（字节）<input type="number" min={104857600} value={draft.clip_quota_bytes || ""} onChange={(e) => setDraft({ ...draft, clip_quota_bytes: Number(e.target.value) })} /></label><label>默认前滚（毫秒）<input type="number" min="0" value={draft.pre_roll_ms || 0} onChange={(e) => setDraft({ ...draft, pre_roll_ms: Number(e.target.value) })} /></label><label>默认后滚（毫秒）<input type="number" min="0" value={draft.post_roll_ms || 0} onChange={(e) => setDraft({ ...draft, post_roll_ms: Number(e.target.value) })} /></label><button className="primary">保存</button></form></section></div></>;
}

type NoticeSetter = (value: { tone: "success" | "error"; text: string } | null) => void;
