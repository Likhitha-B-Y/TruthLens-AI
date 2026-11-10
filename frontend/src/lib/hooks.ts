import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> { data: T | null; error: string | null; loading: boolean; reload: () => void; setData: (d: T | null) => void }

/** Run an async function on mount / when deps change. Ignores stale responses. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  useEffect(() => {
    const my = ++seq.current;
    setLoading(true);
    fn().then((d) => { if (my === seq.current) { setData(d); setError(null); } })
      .catch((e: Error) => { if (my === seq.current) setError(e.message); })
      .finally(() => { if (my === seq.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}

/** Call `fn` every `ms` while `active` is true. */
export function usePoll(fn: () => void | Promise<void>, ms: number, active: boolean) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => void ref.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const id = setTimeout(() => setV(value), ms); return () => clearTimeout(id); }, [value, ms]);
  return v;
}
