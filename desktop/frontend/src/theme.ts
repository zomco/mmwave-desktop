import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
const key = "tracecue.theme.v1";
export function readTheme(value: string | null): Theme {
  return value === "light" || value === "dark" ? value : "system";
}
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try { return readTheme(localStorage.getItem(key)); } catch { return "system"; }
  });
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => { document.documentElement.dataset.theme = theme === "system" ? (media.matches ? "dark" : "light") : theme; };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  const cycleTheme = () => {
    const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    setTheme(next);
    try { localStorage.setItem(key, next); } catch { /* The in-memory theme still works. */ }
  };
  return { theme, cycleTheme };
}
