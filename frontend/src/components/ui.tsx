import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2, RefreshCw, X, type LucideIcon } from "lucide-react";
import { useEffect, useId, type ButtonHTMLAttributes, type ReactNode } from "react";
import { STATUS_META } from "../lib/format";
import type { Status } from "../lib/types";

export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

/* ------------------------------------------------------------------ Logo */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" className="shrink-0">
      <rect width="64" height="64" rx="16" fill="rgb(var(--brand))" />
      <circle cx="30" cy="30" r="14" fill="none" stroke="#fff" strokeWidth="5" />
      <path d="M23 30l5 5 9-10" fill="none" stroke="#2DD4BF" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M41 41l11 11" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
    </svg>
  );
}
export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-display text-xl font-semibold tracking-tight">
        TruthLens<span className="ml-1 text-secondary">AI</span>
      </span>
    </span>
  );
}

/* ---------------------------------------------------------------- Button */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "accent";
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: "sm" | "md" | "lg"; icon?: LucideIcon; loading?: boolean;
}
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-brand-fg hover:brightness-110 shadow-sm",
  accent: "bg-accent text-white hover:brightness-110 shadow-sm",
  secondary: "border border-line bg-surface text-ink hover:bg-sunken",
  ghost: "text-muted hover:bg-sunken hover:text-ink",
  danger: "border border-bad/30 bg-bad-bg/50 text-bad hover:bg-bad-bg",
};
const SIZES = { sm: "h-8 px-3 text-sm gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-base gap-2.5" };

export function Button({ variant = "primary", size = "md", icon: Icon, loading, children, className, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx("focus-ring inline-flex shrink-0 items-center justify-center rounded-xl font-semibold transition active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant], SIZES[size], className)}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

/* ----------------------------------------------------------------- Cards */
export function Card({ children, className, ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("card", className)}>{children}</div>;
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="font-display text-3xl font-semibold sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, hint, icon: Icon, tone = "brand" }: {
  label: string; value: ReactNode; hint?: ReactNode; icon: LucideIcon; tone?: "brand" | "ok" | "bad" | "warn" | "accent" | "secondary";
}) {
  const tones = { brand: "text-ink bg-sunken", ok: "text-ok bg-ok-bg/60", bad: "text-bad bg-bad-bg/60", warn: "text-warn bg-warn-bg/60", accent: "text-accent bg-accent/10", secondary: "text-secondary bg-secondary/10" };
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium leading-tight text-muted">{label}</p>
          <p className="mt-2 font-display text-4xl font-semibold leading-none">{value}</p>
        </div>
        <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", tones[tone])}><Icon className="h-5 w-5" /></span>
      </div>
      {hint && <p className="mt-3 text-xs text-muted">{hint}</p>}
    </Card>
  );
}

/* ---------------------------------------------------------------- Badges */
export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "ok" | "bad" | "warn" | "accent" | "secondary"; className?: string }) {
  const t = { neutral: "bg-sunken text-muted", ok: "bg-ok-bg/70 text-ok", bad: "bg-bad-bg/70 text-bad", warn: "bg-warn-bg/70 text-warn", accent: "bg-accent/10 text-accent", secondary: "bg-secondary/10 text-secondary" };
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", t[tone], className)}>{children}</span>;
}

export function StatusBadge({ status, size = "md" }: { status: Status; size?: "sm" | "md" }) {
  const m = STATUS_META[status];
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full font-semibold", m.bg, m.text, size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm")}>
      <m.Icon className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      {m.label}
    </span>
  );
}

/* --------------------------------------------------------- Loading / empty */
export function Spinner({ className }: { className?: string }) { return <Loader2 className={cx("h-5 w-5 animate-spin text-muted", className)} aria-label="Loading" />; }
export function Skeleton({ className }: { className?: string }) { return <div className={cx("skeleton h-4 w-full", className)} aria-hidden="true" />; }

export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-line px-6 py-14 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-sunken text-muted"><Icon className="h-7 w-7" /></span>
      <h3 className="mt-4 font-display text-xl font-semibold">{title}</h3>
      {body && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, title = "Something went wrong" }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col items-center rounded-2xl border border-bad/30 bg-bad-bg/30 px-6 py-12 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-bad-bg text-bad"><AlertTriangle className="h-6 w-6" /></span>
      <h3 className="mt-4 font-display text-lg font-semibold">{title}</h3>
      <p className="mt-1.5 max-w-lg text-sm text-muted">{message}</p>
      {onRetry && <Button variant="secondary" icon={RefreshCw} className="mt-5" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "bad"; title?: string; children: ReactNode }) {
  const t = { info: "border-secondary/30 bg-secondary/5", warn: "border-warn/30 bg-warn-bg/40", bad: "border-bad/30 bg-bad-bg/40" };
  return (
    <div role={tone === "bad" ? "alert" : "note"} className={cx("rounded-xl border px-4 py-3 text-sm", t[tone])}>
      {title && <p className="mb-0.5 font-semibold">{title}</p>}
      <div className="leading-relaxed text-ink/80">{children}</div>
    </div>
  );
}

/* ----------------------------------------------------------------- Modal */
export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children?: ReactNode; footer?: ReactNode }) {
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[90] grid place-items-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
          <motion.div role="dialog" aria-modal="true" aria-labelledby={id} initial={{ y: 20, scale: 0.97 }} animate={{ y: 0, scale: 1 }} exit={{ y: 10, scale: 0.97 }}
            className="card relative w-full max-w-md p-6 shadow-pop">
            <button onClick={onClose} aria-label="Close" className="focus-ring absolute right-3 top-3 rounded-lg p-1.5 text-muted hover:text-ink"><X className="h-4 w-4" /></button>
            <h2 id={id} className="font-display text-xl font-semibold">{title}</h2>
            <div className="mt-2 text-sm leading-relaxed text-muted">{children}</div>
            {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ConfirmDialog({ open, title, body, confirmLabel = "Delete", busy, onConfirm, onClose }: {
  open: boolean; title: string; body: ReactNode; confirmLabel?: string; busy?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="danger" loading={busy} onClick={onConfirm}>{confirmLabel}</Button></>}>
      {body}
    </Modal>
  );
}

/* ----------------------------------------------------------- Form controls */
export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-2">
      <span><span className="block text-sm font-semibold">{label}</span>{hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}</span>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={cx("focus-ring relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition", checked ? "bg-secondary" : "bg-line")}>
        <span className={cx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
      </button>
    </label>
  );
}

export function SliderField({ label, hint, value, min, max, step, onChange, format }: {
  label: string; hint?: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; format?: (v: number) => string;
}) {
  const id = useId();
  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-semibold">{label}</label>
        <span className="rounded-md bg-sunken px-2 py-0.5 text-sm font-semibold tabular-nums">{format ? format(value) : value}</span>
      </div>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 h-2 w-full cursor-pointer appearance-none rounded-full bg-line accent-[rgb(var(--accent))]" />
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string; icon?: LucideIcon }[]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl bg-sunken p-1">
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cx("focus-ring inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold transition",
            value === o.value ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
          {o.icon && <o.icon className="h-4 w-4" />}{o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ Score bars */
export function ScoreBar({ label, value, tone }: { label: string; value: number; tone: "ok" | "bad" | "warn" }) {
  const bar = { ok: "bg-ok", bad: "bg-bad", warn: "bg-warn" }[tone];
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="font-medium text-muted">{label}</span><span className="font-semibold tabular-nums">{(value * 100).toFixed(1)}%</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-sunken">
        <motion.div className={cx("h-full rounded-full", bar)} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} transition={{ duration: 0.6, ease: "easeOut" }} />
      </div>
    </div>
  );
}
