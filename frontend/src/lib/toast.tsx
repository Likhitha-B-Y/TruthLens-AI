import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info" | "warning";
interface Toast { id: number; kind: Kind; title: string; body?: string }
interface ToastApi { push: (kind: Kind, title: string, body?: string) => void; success: (t: string, b?: string) => void; error: (t: string, b?: string) => void; info: (t: string, b?: string) => void }
const Ctx = createContext<ToastApi | null>(null);

const ICON = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle };
const COLOR = { success: "text-ok", error: "text-bad", info: "text-secondary", warning: "text-warn" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback((kind: Kind, title: string, body?: string) => {
    const id = next.current++;
    setItems((l) => [...l.slice(-3), { id, kind, title, body }]);
    setTimeout(() => dismiss(id), kind === "error" ? 8000 : 4500);
  }, [dismiss]);
  const api = useMemo<ToastApi>(() => ({
    push, success: (t, b) => push("success", t, b), error: (t, b) => push("error", t, b), info: (t, b) => push("info", t, b),
  }), [push]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,380px)] flex-col gap-2" role="status" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => {
            const Icon = ICON[t.kind];
            return (
              <motion.div key={t.id} layout initial={{ opacity: 0, y: 16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 40 }} transition={{ type: "spring", stiffness: 420, damping: 32 }}
                className="card pointer-events-auto flex items-start gap-3 p-3.5 shadow-pop">
                <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${COLOR[t.kind]}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">{t.title}</p>
                  {t.body && <p className="mt-0.5 break-words text-sm text-muted">{t.body}</p>}
                </div>
                <button onClick={() => dismiss(t.id)} className="focus-ring rounded-md p-1 text-muted hover:text-ink" aria-label="Dismiss"><X className="h-4 w-4" /></button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const c = useContext(Ctx);
  if (!c) throw new Error("useToast must be used inside ToastProvider");
  return c;
}
