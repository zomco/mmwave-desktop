import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ApiError } from "./api";

export const card = "ui-card";
export const field = "ui-field";

export function Button({ variant = "secondary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  return <button className={`ui-button ui-button-${variant} ${className}`} {...props} />;
}

export function Header({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <header className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="ui-eyebrow mb-3">{eyebrow}</p><h1 className="text-2xl font-semibold text-ink sm:text-3xl">{title}</h1><p className="mt-2 max-w-3xl text-sm leading-7 text-muted">{description}</p></div>{action}</header>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "positive" | "warning" | "danger" | "neutral" }) {
  const tones = { positive: "bg-brand-600/10 text-accent", warning: "bg-warning-soft text-warning", danger: "bg-danger-soft text-danger", neutral: "bg-soft text-ink" };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Problem({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <div className="my-4 rounded-xl border border-red-200 bg-danger-soft p-4 text-sm text-danger" role="alert"><strong>{error.code}</strong><span className="ml-2">{error.message}</span><p className="mt-1 font-mono text-xs opacity-70">{error.requestId}</p></div>;
}

export function Empty({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className={`${card} grid min-h-72 place-items-center p-8 text-center`}><div><div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-brand-600/20 bg-brand-600/10 text-accent"><Icon name="radar" size={32} /></div><h2 className="mt-5 text-lg font-semibold">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-7 text-muted">{description}</p>{action && <div className="mt-5">{action}</div>}</div></div>;
}

export function Spinner({ label = "处理中" }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-sm" role="status"><i aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />{label}</span>;
}

export type IconName = "radar" | "search" | "devices" | "video" | "settings" | "theme";
const iconPaths: Record<IconName, string> = {
  radar: "M20.3 8.5A9 9 0 1 1 15.5 3.7M16.6 10A5 5 0 1 1 14 7.4M12 12l8-8",
  search: "M20 20l-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  devices: "M3 4h18v13H3zM8 21h8M12 17v4",
  video: "M3 5h18v14H3zM10 9l5 3-5 3z",
  settings: "M4 6h16M4 12h16M4 18h16M8 4v4M16 10v4M10 16v4",
  theme: "M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9",
};
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={iconPaths[name]} /></svg>;
}
