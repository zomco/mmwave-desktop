import { type FormEvent, useEffect, useState } from "react";
import type { NoticeSetter } from "../App";
import { ApiError, api, patch } from "../api";
import { useLoad } from "../hooks";
import { Button, Header, Problem, card, field } from "../ui";
import type { AppSettings } from "../types";

export function SettingsPage({ setNotice }: { setNotice: NoticeSetter }) {
  const status = useLoad(() => api<Record<string, unknown>>("/status"));
  const settings = useLoad(() => api<AppSettings>("/settings"));
  const diagnostics = useLoad(() => api<Record<string, unknown>>("/diagnostics"));
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => { if (settings.data) setDraft(settings.data); }, [settings.data]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!draft) return;
    try { await patch("/settings", draft); await settings.refresh(); setNotice({ tone: "success", text: "本机设置已保存。" }); }
    catch (caught) { setError(caught as ApiError); }
  }
  return <>
    <Header eyebrow="LOCAL SETTINGS" title="设置与诊断" description="主导航只保留事件检索、设备、候选导出。Gateway/Engine 的来源映射与对照评估暂收进高级能力，不干扰当前主流程。" />
    <Problem error={error ?? status.error ?? settings.error ?? diagnostics.error} />
    <div className="grid gap-5 xl:grid-cols-2">
      <form onSubmit={save} className={`${card} p-6`}><h2 className="text-xl font-bold">片段与检索窗口</h2><div className="mt-5 grid gap-4 sm:grid-cols-2">{draft && <><NumberField label="片段配额（字节）" value={draft.clip_quota_bytes} min={104857600} onChange={(value) => setDraft({ ...draft, clip_quota_bytes: value })} /><NumberField label="默认前滚（毫秒）" value={draft.pre_roll_ms} min={0} onChange={(value) => setDraft({ ...draft, pre_roll_ms: value })} /><NumberField label="默认后滚（毫秒）" value={draft.post_roll_ms} min={0} onChange={(value) => setDraft({ ...draft, post_roll_ms: value })} /><NumberField label="首选端口" value={draft.preferred_port} min={1024} max={65535} onChange={(value) => setDraft({ ...draft, preferred_port: value })} /><NumberField label="夜间开始小时（0–23）" value={draft.night_start_hour} min={0} max={23} onChange={(value) => setDraft({ ...draft, night_start_hour: value })} /><NumberField label="夜间结束小时（0–23）" value={draft.night_end_hour} min={0} max={23} onChange={(value) => setDraft({ ...draft, night_end_hour: value })} /></>}</div><p className="mt-3 text-xs leading-5 text-slate-500">“昨晚”和前后夜快捷检索使用本机时区及这里的夜间边界；默认 18:00–次日 06:00。</p><Button className="mt-5" variant="primary" type="submit">保存设置</Button></form>
      <section className={`${card} p-6`}><h2 className="text-xl font-bold">运行状态</h2><pre className="mt-4 max-h-72 overflow-auto rounded-xl bg-[#102e29] p-4 font-mono text-xs leading-6 text-emerald-100">{JSON.stringify(status.data, null, 2)}</pre><a className="mt-4 inline-flex min-h-10 items-center rounded-xl bg-emerald-700 px-4 text-sm font-semibold text-white" href="/api/v1/diagnostics/export" download>下载脱敏诊断 JSON</a></section>
      <section className={`${card} p-6 xl:col-span-2`}><h2 className="text-xl font-bold">高级能力（后续版本）</h2><div className="mt-4 grid gap-4 md:grid-cols-2"><div className="rounded-xl bg-slate-50 p-4"><strong>Gateway / Engine 来源映射</strong><p className="mt-2 text-sm leading-6 text-slate-600">用于接入持续在线的外部传感器时间轴。按需启动的桌面程序不能重建错过的雷达历史，因此当前不放入主导航。</p></div><div className="rounded-xl bg-slate-50 p-4"><strong>对照评估</strong><p className="mt-2 text-sm leading-6 text-slate-600">只有具备人工标注的 golden dataset 和召回率数据后，才能判断筛选是否真正改进；NVR 单一来源不会被包装成“高置信”。</p></div></div></section>
    </div>
  </>;
}

function NumberField({ label, value, min, max, onChange }: { label: string; value: number; min: number; max?: number; onChange: (value: number) => void }) {
  return <label className="text-sm font-semibold text-slate-700">{label}<input className={`${field} mt-2`} type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
