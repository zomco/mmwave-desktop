import { useEffect, useState } from "react";
import type { NoticeSetter } from "../App";
import { ApiError, api } from "../api";
import { useLoad } from "../hooks";
import { eventPresentation, formatDateTime, formatDuration } from "../lib";
import type { Channel, Clip, Nvr } from "../types";
import { Badge, Button, Empty, Header, Problem, Spinner, card } from "../ui";

export function ExportsPage({ setNotice }: { setNotice: NoticeSetter }) {
  const clips = useLoad(() => api<Clip[]>("/clips"));
  const nvrs = useLoad(() => api<Nvr[]>("/nvrs"));
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    if (!nvrs.data) return;
    Promise.all(nvrs.data.map((nvr) => api<Channel[]>(`/nvrs/${nvr.id}/channels`)))
      .then((groups) => setChannels(groups.flat()))
      .catch((caught) => setError(caught as ApiError));
  }, [nvrs.data]);
  useEffect(() => {
    if (!clips.data?.some((clip) => ["queued", "generating"].includes(clip.status))) return;
    const timer = window.setTimeout(() => void clips.refresh(), 1000);
    return () => window.clearTimeout(timer);
  }, [clips.data, clips.refresh]);

  async function remove(clip: Clip) {
    if (!window.confirm("删除这个本地派生片段？NVR 上的原始录像不会删除。")) return;
    try {
      await api(`/clips/${clip.id}`, { method: "DELETE" });
      await clips.refresh();
      setNotice({ tone: "success", text: "本地片段已删除，NVR 原始录像未受影响。" });
    } catch (caught) {
      setError(caught as ApiError);
    }
  }

  function cameraName(clip: Clip) {
    const channel = channels.find((item) => item.id === clip.channel_id);
    if (channel?.alias) return channel.alias;
    if (channel) return `未命名摄像机 · 通道 ${channel.external_channel_id}`;
    return (clip.origin?.channel_label || "手动选择").replace(/^Channel\s*/i, "未命名摄像机 · 通道 ");
  }

  return <>
    <Header eyebrow="CANDIDATE → EXPORT" title="候选与导出" description="每个片段保留来源事件、检索任务、目标区域和摄像机上下文；确认后下载 MP4，再通过系统分享传到手机。" action={<Button onClick={() => clips.refresh()}>刷新状态</Button>} />
    <div className="mb-5 rounded-2xl border border-sky-200 bg-sky-50 px-5 py-4 text-sm leading-6 text-sky-950"><strong>手机传输说明：</strong>TraceCue 服务坚持只绑定 127.0.0.1，手机不能直接访问。请先下载 MP4，再使用 Windows“附近共享”、微信、数据线或你信任的同步工具发送。</div>
    <div className="mb-5 rounded-2xl border border-amber-300 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-950"><strong>时间基准：</strong>下方事件和片段时间均来自 NVR 的事件索引。视频左上角水印由摄像机自身时钟生成；摄像机未与 NVR 同步时，两者可能相差数分钟，但 TraceCue 不会根据水印猜测或挪动事件片段。</div>
    <Problem error={error ?? clips.error ?? nvrs.error} />
    {!clips.loading && clips.data?.length === 0
      ? <Empty title="还没有候选视频" description="在事件检索结果中生成候选视频后，这里会显示其事件与搜索上下文。" />
      : <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">{clips.data?.map((clip) => <article key={clip.id} className={`${card} overflow-hidden`}>
        <div className="aspect-video bg-[#142e29]">{clip.status === "ready" && clip.content_url
          ? <video className="h-full w-full bg-black object-contain" src={clip.content_url} controls preload="metadata" />
          : <div className="grid h-full place-items-center text-emerald-100/70">{["queued", "generating"].includes(clip.status) ? <Spinner label="正在从 NVR 生成候选片段" /> : <span>片段生成失败</span>}</div>}</div>
        <div className="p-5">
          <div className="flex flex-wrap gap-2"><Badge tone={clip.status === "ready" ? "positive" : clip.status === "failed" ? "danger" : "warning"}>{statusLabel(clip.status)}</Badge>{clip.origin?.area_name && <Badge tone="warning">{clip.origin.area_name}</Badge>}</div>
          <h2 className="mt-3 text-lg font-bold">{clip.origin ? cameraName(clip) : "手动时间窗口"}</h2>
          <p className="mt-1 text-sm text-slate-600">NVR 片段 {formatDateTime(clip.requested_window.start_at)} · {formatDuration(clip.requested_window.start_at, clip.requested_window.end_at)}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-xs"><Info label="目标行为" value={clip.origin ? eventPresentation(clip.origin.event_type || clip.origin.classification) : "无关联事件"} /><Info label="摄像机" value={clip.origin ? cameraName(clip) : "手动选择"} /><Info label="NVR 事件时间" value={clip.origin ? formatDateTime(clip.origin.event_window.start_at) : "—"} /><Info label="检索任务" value={clip.origin?.search_job_id?.slice(-10) || "手动生成"} mono /></dl>
          {clip.origin?.candidate_window_capped && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">候选片段已按生成时的最大时长限制截短；完整事件时间仍保留在详情中。</p>}
          <div className="mt-4 flex gap-2">{clip.content_url && <a className="inline-flex min-h-10 flex-1 items-center justify-center rounded-xl bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800" href={clip.content_url} download={`tracecue-${clip.id}.mp4`}>下载 MP4</a>}<Button className="flex-1" variant="danger" onClick={() => remove(clip)}>删除</Button></div>
          {clip.status === "ready" && <p className="mt-3 text-xs text-slate-500">{clip.video_codec || "视频"} · {clip.audio_codec || "无音频/未知"} · {formatBytes(clip.size_bytes)}</p>}
        </div>
      </article>)}</div>}
  </>;
}

function Info({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt className="text-slate-500">{label}</dt><dd className={`mt-1 break-all text-slate-800 ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}

function statusLabel(status: Clip["status"]) {
  return { queued: "等待生成", generating: "生成中", ready: "可播放/下载", failed: "生成失败" }[status];
}

function formatBytes(value: number | null) {
  if (value === null) return "大小未知";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}
