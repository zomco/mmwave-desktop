import { useEffect, useState } from "react";
import { DevicesPage } from "./pages/DevicesPage";
import { ExportsPage } from "./pages/ExportsPage";
import { RadarPage } from "./pages/RadarPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TracePage } from "./pages/TracePage";
import { Button, Icon, type IconName } from "./ui";
import { useTheme } from "./theme";

export type View = "radar" | "trace" | "devices" | "exports" | "settings";
export type NoticeSetter = (value: { tone: "success" | "error"; text: string } | null) => void;

const navigation: { id: View; label: string; detail: string; icon: IconName }[] = [
  { id: "radar", label: "雷达回查", detail: "LIVE", icon: "radar" },
  { id: "trace", label: "事件检索", detail: "冷存档", icon: "search" },
  { id: "devices", label: "设备中心", detail: "NVR", icon: "devices" },
  { id: "exports", label: "候选与导出", detail: "VIDEO", icon: "video" },
  { id: "settings", label: "设置", detail: "LOCAL", icon: "settings" },
];

function initialView(): View {
  const hash = window.location.hash.slice(1);
  if (hash === "radar" || hash === "devices" || hash === "exports" || hash === "settings" || hash === "trace") return hash;
  if (["find", "review"].includes(hash)) return "trace";
  if (hash === "clips") return "exports";
  return "radar";
}

export default function App() {
  const { theme, cycleTheme } = useTheme();
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

  return <div className="min-h-screen lg:grid lg:grid-cols-[250px_minmax(0,1fr)]">
    <a className="ui-skip" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById("main-content")?.focus(); }}>跳到主内容</a>
    <aside className="border-b border-line bg-surface px-4 py-4 lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r lg:px-5 lg:py-7">
      <div className="flex items-center gap-3 px-2 lg:mb-8">
        <div className="grid h-11 w-11 place-items-center rounded-xl border border-brand-600/20 bg-brand-600/10 text-accent"><Icon name="radar" size={24} /></div>
        <div><strong className="block text-lg font-semibold tracking-tight">TraceCue</strong><span className="text-xs text-muted">MMWave · 视频回查</span></div>
      </div>
      <nav className="mt-4 flex gap-2 overflow-x-auto lg:mt-0 lg:block lg:space-y-2" aria-label="主功能">
        {navigation.map((item) => <button key={item.id} onClick={() => navigate(item.id)} aria-current={view === item.id ? "page" : undefined} className="ui-nav shrink-0 lg:w-full"><Icon name={item.icon} /><span className="font-semibold">{item.label}</span><small className="ml-auto hidden text-muted lg:block">{item.detail}</small></button>)}
      </nav>
      <div className="mt-4 flex items-center justify-between gap-2 border-t border-line pt-4 lg:mt-auto lg:flex-col lg:items-stretch">
        <Button onClick={cycleTheme} aria-label={`切换主题，当前${{ system: "跟随系统", light: "浅色", dark: "深色" }[theme]}`}><Icon name="theme" size={16} />{{ system: "跟随系统", light: "浅色", dark: "深色" }[theme]}</Button>
        <p className="text-xs text-muted lg:mt-3">仅本机访问 · 127.0.0.1</p>
      </div>
    </aside>
    <main id="main-content" tabIndex={-1} className="mx-auto min-w-0 w-full max-w-[1500px] px-4 py-7 sm:px-7 lg:px-10 lg:py-11 xl:px-14">
      {notice && <div className={`fixed right-5 top-5 z-50 max-w-md rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-2xl ${notice.tone === "success" ? "bg-brand-600" : "bg-red-700"}`} role="status">{notice.text}</div>}
      {view === "radar" && <RadarPage />}
      {view === "trace" && <TracePage navigate={navigate} setNotice={setNotice} />}
      {view === "devices" && <DevicesPage setNotice={setNotice} />}
      {view === "exports" && <ExportsPage setNotice={setNotice} />}
      {view === "settings" && <SettingsPage setNotice={setNotice} />}
    </main>
  </div>;
}
