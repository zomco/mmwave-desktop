import { useEffect, useState } from "react";
import { DevicesPage } from "./pages/DevicesPage";
import { ExportsPage } from "./pages/ExportsPage";
import { RadarPage } from "./pages/RadarPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TracePage } from "./pages/TracePage";

export type View = "radar" | "trace" | "devices" | "exports" | "settings";
export type NoticeSetter = (value: { tone: "success" | "error"; text: string } | null) => void;

const navigation: { id: View; label: string; detail: string; icon: string }[] = [
  { id: "radar", label: "雷达回查", detail: "LIVE", icon: "◉" },
  { id: "trace", label: "事件检索", detail: "冷存档", icon: "⌁" },
  { id: "devices", label: "设备中心", detail: "NVR", icon: "▣" },
  { id: "exports", label: "候选与导出", detail: "VIDEO", icon: "▶" },
  { id: "settings", label: "设置", detail: "LOCAL", icon: "⚙" },
];

function initialView(): View {
  const hash = window.location.hash.slice(1);
  if (hash === "radar" || hash === "devices" || hash === "exports" || hash === "settings" || hash === "trace") return hash;
  if (["find", "review"].includes(hash)) return "trace";
  if (hash === "clips") return "exports";
  return "radar";
}

export default function App() {
  const [view, setView] = useState<View>(initialView);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  useEffect(() => {
    const listener = () => setView(initialView());
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const navigate = (next: View) => {
    window.location.hash = next;
    setView(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
    <aside className="border-b border-white/10 bg-[#102e29] px-4 py-4 text-white lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:px-5 lg:py-7">
      <div className="flex items-center gap-3 px-2 lg:mb-10">
        <div className="grid h-11 w-11 place-items-center rounded-full border border-emerald-300/60 bg-emerald-300/10 text-xl text-emerald-200">⌁</div>
        <div><strong className="block text-lg tracking-tight">TraceCue</strong><span className="text-[10px] tracking-[0.2em] text-emerald-200/60">EVENT TO TRACE</span></div>
      </div>
      <nav className="mt-4 flex gap-2 overflow-x-auto lg:mt-0 lg:block lg:space-y-2" aria-label="主功能">
        {navigation.map((item) => <button key={item.id} onClick={() => navigate(item.id)} className={`flex min-w-max items-center gap-3 rounded-xl px-3 py-3 text-left transition lg:w-full ${view === item.id ? "bg-emerald-200/15 text-white ring-1 ring-emerald-200/25" : "text-emerald-50/65 hover:bg-white/5 hover:text-white"}`}><span className="grid h-8 w-8 place-items-center rounded-lg bg-black/10 text-sm">{item.icon}</span><span className="font-semibold">{item.label}</span><small className="ml-auto hidden font-mono text-[9px] tracking-wider text-emerald-100/35 lg:block">{item.detail}</small></button>)}
      </nav>
      <div className="mt-auto hidden border-t border-white/10 px-2 pt-5 font-mono text-[10px] text-emerald-100/55 lg:absolute lg:inset-x-5 lg:bottom-6 lg:block"><i className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_0_4px_rgba(110,231,183,.12)]" />仅本机访问 · 127.0.0.1</div>
    </aside>
    <main className="mx-auto w-full max-w-[1500px] px-4 py-7 sm:px-7 lg:px-10 lg:py-11 xl:px-14">
      {notice && <div className={`fixed right-5 top-5 z-50 max-w-md rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-2xl ${notice.tone === "success" ? "bg-emerald-700" : "bg-red-700"}`} role="status">{notice.text}</div>}
      {view === "radar" && <RadarPage />}
      {view === "trace" && <TracePage navigate={navigate} setNotice={setNotice} />}
      {view === "devices" && <DevicesPage setNotice={setNotice} />}
      {view === "exports" && <ExportsPage setNotice={setNotice} />}
      {view === "settings" && <SettingsPage setNotice={setNotice} />}
    </main>
  </div>;
}
