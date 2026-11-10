import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, FlaskConical, History, Library, LayoutDashboard, Loader2, Menu, Moon, ScanSearch, Settings, Sun, WifiOff, X, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useModelStatus } from "../lib/modelStatus";
import { useTheme } from "../lib/theme";
import { Logo, cx } from "./ui";

const NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/verify", label: "New verification", icon: ScanSearch },
  { to: "/app/library", label: "Evidence library", icon: Library },
  { to: "/app/history", label: "History", icon: History },
  { to: "/app/evaluation", label: "Evaluation", icon: FlaskConical },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

function ModelPill() {
  const { status, offline } = useModelStatus();
  let tone = "bg-sunken text-muted", Icon = Loader2, text = "Connecting...", spin = true;
  if (offline) { tone = "bg-bad-bg/70 text-bad"; Icon = WifiOff; text = "Backend offline"; spin = false; }
  else if (status) {
    const { nli, embedding } = status;
    if (nli.state === "error" || embedding.state === "error") { tone = "bg-bad-bg/70 text-bad"; Icon = AlertTriangle; text = "Model problem"; spin = false; }
    else if (nli.state === "loading" || embedding.state === "loading" || nli.state === "not_loaded") { tone = "bg-warn-bg/70 text-warn"; text = "Loading models..."; }
    else if (embedding.state === "fallback") { tone = "bg-warn-bg/70 text-warn"; Icon = AlertTriangle; text = "Fallback retrieval"; spin = false; }
    else { tone = "bg-ok-bg/70 text-ok"; Icon = CheckCircle2; text = "Models ready"; spin = false; }
  }
  return (
    <NavLink to="/app/settings" title="Model status - open Settings" className={cx("focus-ring inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold", tone)}>
      <Icon className={cx("h-3.5 w-3.5", spin && "animate-spin")} />{text}
    </NavLink>
  );
}

function ThemeButton() {
  const { resolved, toggle } = useTheme();
  return (
    <button onClick={toggle} aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}
      className="focus-ring grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface text-muted transition hover:text-ink">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={resolved} initial={{ rotate: -60, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 60, opacity: 0 }} transition={{ duration: 0.18 }}>
          {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} onClick={onNavigate}
          className={({ isActive }) => cx("focus-ring group flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition",
            isActive ? "bg-brand text-brand-fg shadow-sm" : "text-muted hover:bg-sunken hover:text-ink")}>
          <n.icon className="h-[18px] w-[18px]" />{n.label}
        </NavLink>
      ))}
    </nav>
  );
}

export default function AppShell() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const { offline } = useModelStatus();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <div className="min-h-screen lg:pl-64">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-surface px-4 py-5 lg:flex">
        <NavLink to="/" className="focus-ring mb-8 rounded-xl px-2" aria-label="TruthLens AI home"><Logo /></NavLink>
        <NavList />
        <div className="mt-auto rounded-2xl bg-sunken p-4">
          <p className="text-xs font-semibold">Verification, not guesswork</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">Every verdict comes from natural language inference over your documents - never from similarity alone.</p>
        </div>
      </aside>

      {/* top bar */}
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur sm:px-8">
        <div className="flex items-center gap-3 lg:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="focus-ring grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface"><Menu className="h-5 w-5" /></button>
          <Logo className="[&>span:last-child]:hidden sm:[&>span:last-child]:inline" />
        </div>
        <div className="ml-auto flex items-center gap-2"><ModelPill /><ThemeButton /></div>
      </header>

      {/* mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-50 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={() => setOpen(false)} />
            <motion.div className="absolute inset-y-0 left-0 flex w-72 flex-col bg-surface p-5 shadow-pop" initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={{ type: "spring", stiffness: 380, damping: 36 }}>
              <div className="mb-8 flex items-center justify-between">
                <Logo />
                <button onClick={() => setOpen(false)} aria-label="Close menu" className="focus-ring rounded-lg p-1.5 text-muted"><X className="h-5 w-5" /></button>
              </div>
              <NavList onNavigate={() => setOpen(false)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {offline && (
        <div role="alert" className="mx-4 mt-4 flex items-start gap-3 rounded-xl border border-bad/30 bg-bad-bg/40 px-4 py-3 text-sm sm:mx-8">
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
          <p><b>Cannot reach the backend.</b> Start it with <code className="rounded bg-sunken px-1.5 py-0.5">start.bat</code> (or <code className="rounded bg-sunken px-1.5 py-0.5">./start.sh</code>), then this page reconnects automatically.</p>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={loc.pathname} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
