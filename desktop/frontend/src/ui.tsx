import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ApiError } from "./api";

export const card = "rounded-2xl border border-slate-200/90 bg-white/90 shadow-[0_16px_60px_rgba(15,43,38,0.06)] backdrop-blur";
export const field = "min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100";

export function Button({ variant = "secondary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const variants = {
    primary: "border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800",
    secondary: "border-slate-300 bg-white text-slate-700 hover:border-emerald-500 hover:text-emerald-800",
    danger: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
    ghost: "border-transparent bg-transparent text-slate-600 hover:bg-slate-100",
  };
  return <button className={`inline-flex min-h-10 items-center justify-center rounded-xl border px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]} ${className}`} {...props} />;
}

export function Header({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <header className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 font-mono text-[11px] font-semibold tracking-[0.18em] text-emerald-700">{eyebrow}</p><h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">{title}</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p></div>{action}</header>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "positive" | "warning" | "danger" | "neutral" }) {
  const tones = { positive: "bg-emerald-100 text-emerald-800", warning: "bg-amber-100 text-amber-800", danger: "bg-red-100 text-red-800", neutral: "bg-slate-100 text-slate-700" };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Problem({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <div className="my-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert"><strong>{error.code}</strong><span className="ml-2">{error.message}</span><p className="mt-1 font-mono text-xs opacity-70">{error.requestId}</p></div>;
}

export function Empty({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className={`${card} grid min-h-72 place-items-center p-8 text-center`}><div><div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-2xl text-emerald-700">⌁</div><h2 className="mt-5 text-lg font-bold">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600">{description}</p>{action && <div className="mt-5">{action}</div>}</div></div>;
}

export function Spinner({ label = "处理中" }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-sm text-slate-600"><i className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-emerald-700" />{label}</span>;
}
