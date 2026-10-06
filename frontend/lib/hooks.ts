"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export function useApi<T = any>(path: string | null, opts: { poll?: number; deps?: any[] } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const alive = useRef(true);
  const load = useCallback(
    async (silent = false) => {
      if (!path) return;
      if (!silent) setLoading(true);
      try {
        const d = await api<T>(path);
        if (alive.current) {
          setData(d);
          setError(null);
        }
      } catch (e: any) {
        if (alive.current) setError(e.message || "Request failed");
      } finally {
        if (alive.current) setLoading(false);
      }
    },
    [path]
  );
  useEffect(() => {
    alive.current = true;
    load();
    let t: any;
    if (opts.poll) t = setInterval(() => load(true), opts.poll);
    return () => {
      alive.current = false;
      if (t) clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, opts.poll, ...(opts.deps || [])]);
  return { data, error, loading, reload: () => load(true), setData };
}

export function useAction<A extends any[], R>(fn: (...a: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (...a: A) => {
      setBusy(true);
      setError(null);
      try {
        return await fn(...a);
      } catch (e: any) {
        setError(e.message || "Failed");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn]
  );
  return { run, busy, error, setError };
}
