import { type FormEvent, useEffect, useState } from "react";
import type { NoticeSetter } from "../App";
import { ApiError, api, patch, post } from "../api";
import { useLoad } from "../hooks";
import { nvrProbePayload, type NvrConnectionForm } from "../lib";
import type { Channel, DiscoveredDevice, EventAudit, Nvr } from "../types";
import { Badge, Button, Header, Problem, Spinner, card, field } from "../ui";

const emptyForm: NvrConnectionForm = { name: "", host: "", username: "", password: "", http_port: 80, use_https: false, verify_tls: true };

export function DevicesPage({ setNotice }: { setNotice: NoticeSetter }) {
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const [discovered, setDiscovered] = useState<DiscoveredDevice[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [form, setForm] = useState<NvrConnectionForm>(emptyForm);
  const [probe, setProbe] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [channels, setChannels] = useState<Record<string, Channel[]>>({});
  const [audits, setAudits] = useState<Record<string, EventAudit>>({});
  const [auditBusy, setAuditBusy] = useState<string | null>(null);

  useEffect(() => { void discover(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    for (const nvr of nvrs.data ?? []) {
      api<Channel[]>(`/nvrs/${nvr.id}/channels`).then((items) => setChannels((current) => ({ ...current, [nvr.id]: items }))).catch(() => undefined);
      api<EventAudit>(`/nvrs/${nvr.id}/event-audit`).then((audit) => setAudits((current) => ({ ...current, [nvr.id]: audit }))).catch(() => undefined);
    }
  }, [nvrs.data]);

  async function discover() {
    setDiscovering(true); setError(null);
    try { setDiscovered(await post<DiscoveredDevice[]>("/nvrs/discover", { timeout_seconds: 5 })); }
    catch (caught) { setError(caught as ApiError); }
    finally { setDiscovering(false); }
  }

  function choose(device: DiscoveredDevice) {
    setForm({ ...emptyForm, name: device.model || device.name.replace(/^ISAPI candidate /, "NVR "), host: device.host, http_port: device.http_port, use_https: device.use_https, verify_tls: device.use_https });
    setProbe(null);
    document.getElementById("device-credentials")?.scrollIntoView({ behavior: "smooth" });
  }

  async function readOnlyProbe() {
    setBusy(true); setError(null);
    try { setProbe(await post("/nvrs/probe", nvrProbePayload(form))); setNotice({ tone: "success", text: "只读检测通过，设备身份和时钟已确认。" }); }
    catch (caught) { setError(caught as ApiError); }
    finally { setBusy(false); }
  }

  async function add(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      await post("/nvrs", form);
      setForm(emptyForm); setProbe(null);
      await nvrs.refresh(); await discover();
      setNotice({ tone: "success", text: "NVR 已添加，凭据已写入 Windows 安全存储。" });
    } catch (caught) { setError(caught as ApiError); }
    finally { setBusy(false); }
  }

  async function sync(nvr: Nvr) {
    try {
      const items = await post<Channel[]>(`/nvrs/${nvr.id}/sync-channels`);
      setChannels((current) => ({ ...current, [nvr.id]: items }));
      setNotice({ tone: "success", text: `已同步 ${items.length} 个摄像机通道。` });
    } catch (caught) { setError(caught as ApiError); }
  }

  async function audit(nvr: Nvr) {
    setAuditBusy(nvr.id);
    try {
      const report = await post<EventAudit>(`/nvrs/${nvr.id}/event-audit`);
      setAudits((current) => ({ ...current, [nvr.id]: report }));
      setNotice({ tone: "success", text: "只读事件配置扫描完成。" });
    } catch (caught) { setError(caught as ApiError); }
    finally { setAuditBusy(null); }
  }

  async function auditAll() {
    const configured = nvrs.data ?? [];
    if (!configured.length) return;
    setAuditBusy("all"); setError(null);
    try {
      const next = { ...audits };
      // Run sequentially so embedded recorders are not flooded with rule requests.
      for (const nvr of configured) next[nvr.id] = await post<EventAudit>(`/nvrs/${nvr.id}/event-audit`);
      setAudits(next);
      setNotice({ tone: "success", text: `已完成 ${configured.length} 台 NVR 的只读事件配置扫描。` });
    } catch (caught) { setError(caught as ApiError); }
    finally { setAuditBusy(null); }
  }

  async function rename(channel: Channel) {
    const alias = window.prompt("业务区域/摄像机别名", channel.alias || channel.device_name);
    if (alias === null) return;
    try {
      const updated = await patch<Channel>(`/channels/${channel.id}`, { alias: alias.trim() || null });
      setChannels((current) => ({ ...current, [channel.nvr_id]: (current[channel.nvr_id] ?? []).map((item) => item.id === channel.id ? updated : item) }));
    } catch (caught) { setError(caught as ApiError); }
  }

  async function remove(nvr: Nvr) {
    if (!window.confirm(`删除“${nvr.name}”？关联搜索记录与本地派生片段也会删除，NVR 原始录像不受影响。`)) return;
    try { await api(`/nvrs/${nvr.id}`, { method: "DELETE" }); await nvrs.refresh(); await discover(); setNotice({ tone: "success", text: "设备及本地关联数据已删除，NVR 原始录像未改动。" }); }
    catch (caught) { setError(caught as ApiError); }
  }

  return <>
    <Header eyebrow="DEVICE CENTER" title="设备中心" description="自动搜索局域网内的 ONVIF 与海康 ISAPI 候选设备；选择设备后只需输入用户名和密码。" action={<div className="flex flex-wrap gap-2"><Button onClick={auditAll} disabled={auditBusy !== null || !nvrs.data?.length}>{auditBusy === "all" ? "扫描事件配置中…" : "扫描所有事件配置"}</Button><Button onClick={discover} disabled={discovering}>{discovering ? "扫描设备中…" : "重新扫描局域网"}</Button></div>} />
    <Problem error={error ?? nvrs.error} />
    <section className={`${card} p-5 sm:p-7`}>
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-bold">局域网设备</h2><p className="mt-1 text-sm text-slate-600">ONVIF WS-Discovery 优先；若设备未启用 ONVIF，则只读扫描本机直接连接的私有 /24 网段端口 80。</p></div>{discovering && <Spinner label="正在发现设备（最多 5 秒）" />}</div>
      {!discovering && discovered.length === 0 ? <div className="mt-5 rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-600">没有自动发现设备。可能位于不同 VLAN、关闭了 ONVIF、使用非 80 端口；可在下方手动填写地址。</div> : <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{discovered.map((device) => <button type="button" key={`${device.host}:${device.http_port}:${device.use_https}`} onClick={() => choose(device)} disabled={device.already_added} className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-emerald-500 hover:bg-emerald-50 disabled:cursor-default disabled:opacity-60"><div className="flex items-start justify-between gap-2"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#173b34] text-white">▣</span><Badge tone={device.already_added ? "positive" : device.discovery_protocol === "onvif_ws_discovery" ? "positive" : "warning"}>{device.already_added ? "已添加" : device.discovery_protocol === "onvif_ws_discovery" ? "ONVIF" : "待验证 ISAPI"}</Badge></div><strong className="mt-3 block truncate">{device.model || device.name}</strong><span className="mt-1 block font-mono text-xs text-slate-500">{device.use_https ? "https" : "http"}://{device.host}:{device.http_port}</span></button>)}</div>}
    </section>
    <form id="device-credentials" onSubmit={add} className={`${card} mt-5 p-5 sm:p-7`}>
      <div className="mb-5"><h2 className="text-xl font-bold">验证并添加</h2><p className="mt-1 text-sm text-slate-600">只读检测不会保存凭据；确认添加后，密码仅进入 Windows DPAPI 安全存储，不写入 SQLite 或日志。</p></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"><Field label="显示名称" value={form.name} onChange={(name) => setForm({ ...form, name })} placeholder="例如：一号楼 NVR" /><Field label="NVR 地址" value={form.host} onChange={(host) => setForm({ ...form, host })} placeholder="192.168.1.64" /><label className="text-sm font-semibold text-slate-700">HTTP(S) 端口<input required type="number" min="1" max="65535" className={`${field} mt-2`} value={form.http_port} onChange={(event) => setForm({ ...form, http_port: Number(event.target.value) })} /></label><Field label="用户名" value={form.username} onChange={(username) => setForm({ ...form, username })} autoComplete="username" /><Field label="密码" value={form.password} onChange={(password) => setForm({ ...form, password })} type="password" autoComplete="current-password" /></div>
      <div className="mt-5 flex flex-wrap gap-5"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.use_https} onChange={(event) => setForm({ ...form, use_https: event.target.checked })} />使用 HTTPS</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.verify_tls} disabled={!form.use_https} onChange={(event) => setForm({ ...form, verify_tls: event.target.checked })} />验证 TLS 证书</label></div>
      {probe && <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><strong>只读检测已通过</strong><p className="mt-1">可以确认添加；具体型号、固件、时钟与能力证据会随设备记录保存。</p></div>}
      <div className="mt-5 flex gap-3"><Button type="button" onClick={readOnlyProbe} disabled={busy || !form.host || !form.username || !form.password}>只读检测</Button><Button variant="primary" type="submit" disabled={busy || !form.host || !form.username || !form.password}>{busy ? "处理中…" : "确认添加"}</Button></div>
    </form>
    <section className="mt-8"><h2 className="mb-4 text-2xl font-bold">已配置设备 <span className="text-base font-normal text-slate-500">{nvrs.data?.length ?? 0}</span></h2><div className="space-y-5">{nvrs.data?.map((nvr) => <ConfiguredDevice key={nvr.id} nvr={nvr} channels={channels[nvr.id] ?? []} audit={audits[nvr.id]} auditBusy={auditBusy === nvr.id || auditBusy === "all"} onSync={() => sync(nvr)} onAudit={() => audit(nvr)} onRename={rename} onRemove={() => remove(nvr)} />)}</div></section>
  </>;
}

function Field({ label, onChange, ...props }: { label: string; onChange: (value: string) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange">) {
  return <label className="text-sm font-semibold text-slate-700">{label}<input required className={`${field} mt-2`} onChange={(event) => onChange(event.target.value)} {...props} /></label>;
}

function ConfiguredDevice({ nvr, channels, audit, auditBusy, onSync, onAudit, onRename, onRemove }: { nvr: Nvr; channels: Channel[]; audit?: EventAudit; auditBusy: boolean; onSync: () => void; onAudit: () => void; onRename: (channel: Channel) => void; onRemove: () => void }) {
  const enabled = audit?.rules.filter((rule) => rule.enabled).length ?? 0;
  const notifications = audit?.rules.filter((rule) => rule.notification_configured).length ?? 0;
  return <article className={`${card} p-5 sm:p-7`}><div className="flex flex-wrap items-start justify-between gap-4"><div className="flex gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-100 text-emerald-800">▣</span><div><div className="flex flex-wrap items-center gap-2"><h3 className="text-lg font-bold">{nvr.name}</h3><Badge tone="positive">已连接</Badge></div><p className="mt-1 font-mono text-xs text-slate-500">{nvr.model || "型号未知"} · {nvr.firmware || "固件未知"} · {nvr.host}:{nvr.http_port}</p></div></div><div className="flex flex-wrap gap-2"><Button onClick={onSync}>同步通道</Button><Button onClick={onAudit} disabled={auditBusy}>{auditBusy ? "扫描配置中…" : "扫描事件配置"}</Button><Button variant="danger" onClick={onRemove}>删除设备</Button></div></div>
    <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <div><h4 className="mb-2 text-sm font-bold">摄像机与业务区域</h4><div className="divide-y divide-slate-100 rounded-xl border border-slate-200">{channels.map((channel) => <button type="button" key={channel.id} onClick={() => onRename(channel)} className="flex w-full items-center justify-between gap-3 bg-white px-4 py-3 text-left text-sm first:rounded-t-xl last:rounded-b-xl hover:bg-slate-50"><span><strong>{channel.alias || channel.device_name}</strong><small className="ml-2 font-mono text-slate-400">#{channel.external_channel_id}</small></span><span className="text-xs text-slate-500">{channel.online ? "在线" : "状态未知/离线"} · 编辑别名</span></button>)}{channels.length === 0 && <p className="p-4 text-sm text-slate-500">尚未同步到通道。</p>}</div></div>
      <div><div className="mb-2 flex items-center justify-between"><h4 className="text-sm font-bold">事件与通知配置</h4>{audit && <span className="text-xs text-slate-500">启用 {enabled} · 通知联动 {notifications}</span>}</div>{!audit ? <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm leading-6 text-slate-600">点击“扫描事件配置”，只读检查移动侦测、越界、区域入侵以及设备端通知联动。不会修改 NVR。</div> : <div className="max-h-64 overflow-auto rounded-xl border border-slate-200"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><th className="p-3">通道</th><th className="p-3">事件</th><th className="p-3">启用</th><th className="p-3">通知</th><th className="p-3">规则</th></tr></thead><tbody className="divide-y divide-slate-100">{audit.rules.map((rule, index) => <tr key={`${rule.channel_external_id}-${rule.event_type}-${index}`}><td className="p-3">{rule.channel_label}</td><td className="p-3 font-mono">{rule.event_type}</td><td className="p-3"><Badge tone={rule.enabled ? "positive" : rule.state === "unsupported" ? "neutral" : "warning"}>{rule.enabled === null ? rule.state : rule.enabled ? "已启用" : "未启用"}</Badge></td><td className="p-3">{rule.notification_configured === null ? "未知" : rule.notification_configured ? "已配置" : "未配置"}</td><td className="p-3">{rule.region_count ?? "—"} 区域</td></tr>)}</tbody></table></div>}</div>
    </div>
  </article>;
}
