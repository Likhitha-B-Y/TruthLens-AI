import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import type { ModelsStatus } from "./types";

interface Ctx { status: ModelsStatus | null; offline: boolean; refresh: () => Promise<void>; reload: () => Promise<void> }
const C = createContext<Ctx | null>(null);

export function ModelStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ModelsStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const refresh = useCallback(async () => {
    try { setStatus(await api.modelsStatus()); setOffline(false); } catch { setOffline(true); }
  }, []);
  const reload = useCallback(async () => { try { setStatus(await api.reloadModels()); setOffline(false); } catch { setOffline(true); } }, []);

  useEffect(() => {
    let alive = true;
    const loop = async () => {
      await refresh();
      if (alive) timer.current = setTimeout(loop, 2500);
    };
    void loop();
    return () => { alive = false; if (timer.current) clearTimeout(timer.current); };
  }, [refresh]);

  const value = useMemo(() => ({ status, offline, refresh, reload }), [status, offline, refresh, reload]);
  return <C.Provider value={value}>{children}</C.Provider>;
}

export function useModelStatus(): Ctx {
  const c = useContext(C);
  if (!c) throw new Error("useModelStatus must be used inside ModelStatusProvider");
  return c;
}
