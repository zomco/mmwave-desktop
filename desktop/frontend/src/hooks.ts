import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./api";
import type { Job } from "./types";

export function useLoad<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
      setError(null);
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }, dependencies); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void refresh(), [refresh]);
  return { data, error, loading, refresh, setData };
}

export function useJob(job: Job | null, onSettled?: (job: Job) => void) {
  const [current, setCurrent] = useState<Job | null>(job);
  useEffect(() => setCurrent(job), [job]);
  useEffect(() => {
    if (!current || !["queued", "running"].includes(current.state)) return;
    const timer = window.setTimeout(async () => {
      const next = await api<Job>(`/jobs/${current.id}`);
      setCurrent(next);
      if (!["queued", "running"].includes(next.state)) onSettled?.(next);
    }, 700);
    return () => window.clearTimeout(timer);
  }, [current, onSettled]);
  return current;
}
