// Development-only entry. Vite's production input remains index.html.
import { createRoot } from "react-dom/client";
import { useState } from "react";
import App from "../src/App";
import { EventTimeline, type TimelineWindow } from "../src/EventTimeline";
import { Button, Badge, card, field } from "../src/ui";
import type { Channel, Nvr } from "../src/types";
import "../src/styles.css";

const settings = {clip_quota_bytes:1073741824,pre_roll_ms:2000,post_roll_ms:5000,preferred_port:8765,night_start_hour:18,night_end_hour:6};
const fixtures: Record<string, unknown> = {
  "/settings":settings, "/status":{service:"TraceCue visual fixture",storage:"simulation",visual_analysis:{available:false}}, "/diagnostics":{}, "/nvrs":[], "/clips":[], "/search-presets":[],
  "/fusion-events":{available:true,events:[]},
  "/nvrs/discover":[{host:"192.0.2.10",http_port:80,use_https:false,name:"模拟 NVR",model:"NVR · Preview",device_types:[],discovery_protocol:"onvif_ws_discovery",already_added:false}],
};
// ?populated exercises the real search form without a recorder or camera stream.
if (new URLSearchParams(location.search).has("populated")) {
  const nvr: Nvr = {id:"preview",name:"模拟 NVR",host:"192.0.2.10",http_port:80,use_https:false,verify_tls:true,model:"Preview",firmware:null,timezone:"Asia/Shanghai",clock_skew_ms:0,utc_offset_minutes:480};
  const channel: Channel = {id:"preview-door",nvr_id:nvr.id,external_channel_id:"1",primary_track_id:null,stream_track_ids:[],device_name:"门口 · 模拟摄像机",alias:null,online:true};
  fixtures["/nvrs"] = [nvr];
  fixtures["/nvrs/preview/channels"] = [channel];
  fixtures["/nvrs/preview/event-audit"] = {schema_version:1,observed_at:"2026-10-15T01:00:00Z",rules:[],warnings:[]};
}
// Never fall through to the real API: fixtures fail closed for every request.
window.fetch = async (input, init) => {
  const path = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.origin).pathname.replace("/api/v1", "");
  const method = init?.method ?? "GET";
  const allowed = method === "GET" || path === "/nvrs/discover";
  const body = allowed && path in fixtures ? fixtures[path] : {error:{code:"VISUAL_FIXTURE",message:"视觉验收模式不执行设备操作。",request_id:"fixture",details:{}}};
  return new Response(JSON.stringify(body),{status:allowed && path in fixtures ? 200 : 409,headers:{"Content-Type":"application/json"}});
};
const windowFixture = {start_at:"2026-10-15T01:00:00Z",end_at:"2026-10-15T01:10:00Z"};
const events = Array.from({length:15},(_,i)=>({id:`demo-${i}`,start_at:new Date(Date.parse(windowFixture.start_at)+i*35000).toISOString(),end_at:new Date(Date.parse(windowFixture.start_at)+i*35000+12000).toISOString(),duration_ms:12000,cluster_size:1}));
function VisualFixture() {
  const [selected,setSelected] = useState<TimelineWindow|null>(null);
  return <><App /><section className={`${card} m-4 p-6`}><h2 className="mb-4 text-xl font-semibold">图形与控件状态样本</h2><EventTimeline events={events} from={windowFixture.start_at} to={windowFixture.end_at} selected={selected} onSelect={setSelected} /><div className="mt-5 flex flex-wrap gap-3"><Button variant="primary">主要操作</Button><Button>次要操作</Button><Button variant="danger">危险操作</Button><Button disabled>不可用</Button><Badge tone="positive">在线</Badge><Badge tone="warning">待验证</Badge><Badge tone="danger">失败</Badge></div><label className="mt-5 block">输入示例<input className={`${field} mt-2 max-w-sm`} placeholder="名称或设备地址" /></label></section></>;
}
createRoot(document.getElementById("root")!).render(<VisualFixture />);
