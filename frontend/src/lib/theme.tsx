import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemePref = "light" | "dark" | "system";
interface ThemeCtx { pref: ThemePref; resolved: "light" | "dark"; setPref: (t: ThemePref) => void; toggle: () => void }
const Ctx = createContext<ThemeCtx | null>(null);
const KEY = "truthlens-theme";

const systemDark = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(() => (localStorage.getItem(KEY) as ThemePref) || "system");
  const [sys, setSys] = useState(systemDark());
  const resolved: "light" | "dark" = pref === "system" ? (sys ? "dark" : "light") : pref;

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const h = () => setSys(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);
  useEffect(() => { document.documentElement.classList.toggle("dark", resolved === "dark"); }, [resolved]);

  const setPref = useCallback((t: ThemePref) => { localStorage.setItem(KEY, t); setPrefState(t); }, []);
  const toggle = useCallback(() => setPref(resolved === "dark" ? "light" : "dark"), [resolved, setPref]);
  const value = useMemo(() => ({ pref, resolved, setPref, toggle }), [pref, resolved, setPref, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useTheme must be used inside ThemeProvider");
  return c;
}
