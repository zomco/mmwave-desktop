import { useEffect, useState } from "react";
import QRCode from "qrcode";
import type { NoticeSetter } from "../App";
import { ApiError, api, post } from "../api";
import { useLoad } from "../hooks";
import { eventPresentation, formatDateTime, formatDuration } from "../lib";
import type { Clip, ClipShare } from "../types";
import { Badge, Button, Empty, Header, Problem, Spinner, card } from "../ui";

type ShareView = { share: ClipShare; qrDataUrl: string };

export function ExportsPage({ setNotice }: { setNotice: NoticeSetter }) {
  const clips = useLoad(() => api<Clip[]>("/clips"));
  const [error, setError] = useState<ApiError | null>(null);
  const [shares, setShares] = useState<Record<string, ShareView>>({});
  const [sharing, setSharing] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!clips.data?.some((clip) => ["queued", "generating"].includes(clip.status))) return;
    const timer = window.setTimeout(() => void clips.refresh(), 700);
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

  async function share(clip: Clip) {
    setSharing(clip.id);
    setError(null);
    try {
      const value = await post<ClipShare>(`/clips/${clip.id}/share`);
      const qrDataUrl = await QRCode.toDataURL(value.url, {
        width: 260,
        margin: 1,
        errorCorrectionLevel: "M",
        color: { dark: "#102e29", light: "#ffffff" },
      });
      setShares((current) => ({ ...current, [clip.id]: { share: value, qrDataUrl } }));
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setSharing(null);
    }
  }

  async function download(clip: Clip) {
    if (!clip.content_url) return;
    setError(null);
    setDownloadProgress((current) => ({ ...current, [clip.id]: 0 }));
    try {
      const response = await fetch(clip.content_url);
      if (!response.ok || !response.body) throw new Error("download failed");
      const total = Number(response.headers.get("Content-Length") ?? clip.size_bytes ?? 0);
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.byteLength;
        setDownloadProgress((current) => ({
          ...current,
          [clip.id]: total > 0 ? Math.min(1, received / total) : 0,
        }));
      }
      const blob = new Blob(chunks as BlobPart[], { type: "video/mp4" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `tracecue-${clip.id}.mp4`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      setDownloadProgress((current) => ({ ...current, [clip.id]: 1 }));
      setNotice({ tone: "success", text: "MP4 已下载到浏览器的默认下载位置。" });
    } catch {
      setDownloadProgress((current) => { const next = { ...current }; delete next[clip.id]; return next; });
      setError(new ApiError("MEDIA_DOWNLOAD_FAILED", "视频下载未完成，请重试。", "req_local", 0, {}));
    }
  }

  function cameraName(clip: Clip) {
    return (clip.origin?.channel_label || "手动时间窗口")
      .replace(/^Channel\s*/i, "未命名摄像机 · 通道 ");
  }

  return <>
    <Header eyebrow="CANDIDATE → EXPORT" title="候选与导出" description="确认事件片段后可查看生成进度、下载 MP4，或临时分享给同一局域网内的手机。" action={<Button onClick={() => clips.refresh()}>刷新状态</Button>} />
    <div className="mb-5 rounded-2xl border border-sky-200 bg-sky-50 px-5 py-4 text-sm leading-6 text-sky-950"><strong>手机二维码：</strong>点击后才会开启只读临时分享。二维码使用随机令牌、仅能访问当前片段，15 分钟后失效；主 API 仍只监听 127.0.0.1。Windows 防火墙首次可能请求允许当前专用网络访问。</div>
    <div className="mb-5 rounded-2xl border border-amber-300 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-950"><strong>时间基准：</strong>事件和片段时间均来自 NVR 事件索引。视频水印由摄像机自身时钟生成；摄像机未与 NVR 同步时可能存在偏差。</div>
    <Problem error={error ?? clips.error} />
    {!clips.loading && clips.data?.length === 0
      ? <Empty title="还没有候选视频" description="在事件检索结果中生成候选视频后，这里会显示可播放片段。" />
      : <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">{clips.data?.map((clip) => {
        const generationProgress = Math.max(0, Math.min(1, clip.progress ?? 0));
        const transferProgress = downloadProgress[clip.id];
        const shared = shares[clip.id];
        return <article key={clip.id} className={`${card} overflow-hidden`}>
          <div className="aspect-video bg-[#142e29]">{clip.status === "ready" && clip.content_url
            ? <video className="h-full w-full bg-black object-contain" src={clip.content_url} controls preload="metadata" />
            : <div className="grid h-full place-items-center px-8 text-emerald-100/70">{["queued", "generating"].includes(clip.status) ? <div className="w-full"><Spinner label="正在从 NVR 生成候选片段" /><ProgressBar value={generationProgress} label="片段生成进度" dark /></div> : <span>片段生成失败</span>}</div>}</div>
          <div className="p-5">
            <div className="flex flex-wrap gap-2"><Badge tone={clip.status === "ready" ? "positive" : clip.status === "failed" ? "danger" : "warning"}>{statusLabel(clip.status)}</Badge>{clip.origin?.area_name && <Badge tone="warning">{clip.origin.area_name}</Badge>}</div>
            <h2 className="mt-3 text-lg font-bold">{clip.origin ? cameraName(clip) : "手动时间窗口"}</h2>
            <p className="mt-1 text-sm text-slate-600">{formatDateTime(clip.requested_window.start_at)} · {formatDuration(clip.requested_window.start_at, clip.requested_window.end_at)}</p>
            <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs"><span className="text-slate-500">目标行为</span><strong className="ml-3 text-slate-800">{clip.origin ? eventPresentation(clip.origin.event_type || clip.origin.classification) : "无关联事件"}</strong></div>
            {clip.origin?.candidate_window_capped && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">片段已按生成时的最大时长限制截短。</p>}
            {transferProgress !== undefined && transferProgress < 1 && <ProgressBar value={transferProgress} label="下载到电脑" />}
            <div className="mt-4 grid grid-cols-2 gap-2">
              {clip.content_url && <Button variant="primary" disabled={transferProgress !== undefined && transferProgress < 1} onClick={() => void download(clip)}>{transferProgress !== undefined && transferProgress < 1 ? `下载 ${Math.round(transferProgress * 100)}%` : "下载 MP4"}</Button>}
              {clip.content_url && <Button disabled={sharing === clip.id} onClick={() => void share(clip)}>{sharing === clip.id ? "生成中…" : shared ? "刷新二维码" : "手机二维码"}</Button>}
              <Button className="col-span-2" variant="danger" onClick={() => remove(clip)}>删除</Button>
            </div>
            {shared && <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-center"><img className="mx-auto h-56 w-56 rounded-lg bg-white p-2" src={shared.qrDataUrl} alt="手机查看视频二维码" /><p className="mt-2 text-xs leading-5 text-emerald-900">手机连接同一局域网后，用微信扫一扫。有效至 {formatDateTime(shared.share.expires_at)}。</p></div>}
            {clip.status === "ready" && <p className="mt-3 text-xs text-slate-500">{clip.video_codec || "视频"} · {clip.audio_codec || "无音频/未知"} · {formatBytes(clip.size_bytes)}</p>}
          </div>
        </article>;
      })}</div>}
  </>;
}

function ProgressBar({ value, label, dark = false }: { value: number; label: string; dark?: boolean }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)));
  return <div className="mt-3" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><div className={`h-2 overflow-hidden rounded-full ${dark ? "bg-white/15" : "bg-slate-200"}`}><div className="h-full rounded-full bg-emerald-400 transition-[width]" style={{ width: `${Math.max(3, percent)}%` }} /></div><p className={`mt-1 text-center font-mono text-[10px] ${dark ? "text-emerald-100/70" : "text-slate-500"}`}>{label} {percent}%</p></div>;
}

function statusLabel(status: Clip["status"]) {
  return { queued: "等待生成", generating: "生成中", ready: "可播放/下载", failed: "生成失败" }[status];
}

function formatBytes(value: number | null) {
  if (value === null) return "大小未知";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}
