import { motion } from "framer-motion";
import { CheckCircle2, CircleHelp, Clock, Download, FileText, Flag, ListChecks, Plus, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ClaimCard from "../components/ClaimCard";
import { StackedBar } from "../components/Charts";
import { Button, Card, EmptyState, ErrorState, Notice, PageHeader, Skeleton, StatCard, cx } from "../components/ui";
import { api } from "../lib/api";
import { STAGE_LABELS, formatDate, seconds } from "../lib/format";
import { useAsync, usePoll } from "../lib/hooks";
import { useToast } from "../lib/toast";
import type { Status } from "../lib/types";

type Filter = "ALL" | Status | "REVIEW";

export default function Results() {
  const { id = "" } = useParams();
  const toast = useToast();
  const s = useAsync(() => api.session(id), [id]);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [busy, setBusy] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);

  const session = s.data;
  const inFlight = session && (session.status === "queued" || session.status === "running");
  usePoll(() => s.reload(), 1000, !!inFlight);
  useEffect(() => { setFilter("ALL"); }, [id]);

  const claims = session?.claims ?? [];
  const sum = session?.summary ?? {};
  const counts = useMemo(() => ({
    ALL: claims.length,
    SUPPORTED: claims.filter((c) => c.status === "SUPPORTED").length,
    CONTRADICTED: claims.filter((c) => c.status === "CONTRADICTED").length,
    INSUFFICIENT_EVIDENCE: claims.filter((c) => c.status === "INSUFFICIENT_EVIDENCE").length,
    REVIEW: claims.filter((c) => c.needs_review).length,
  }), [claims]);
  const shown = claims.filter((c) => (filter === "ALL" ? true : filter === "REVIEW" ? c.needs_review : c.status === filter));

  const download = async () => {
    setBusy(true);
    try {
      const blob = await api.downloadReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `TruthLens-report-${id}.pdf`; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast.success("Report downloaded");
    } catch (e) { toast.error("Could not generate the report", (e as Error).message); }
    finally { setBusy(false); }
  };

  if (s.loading && !session) return (<><PageHeader title="Verification results" /><div className="grid gap-4 sm:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="mt-6 h-64" /></>);
  if (s.error || !session) return (<><PageHeader title="Verification results" /><ErrorState title={s.error?.includes("not found") ? "Session not found" : "Could not load results"} message={s.error ?? "Unknown error"} onRetry={s.reload} /></>);

  if (inFlight) {
    const p = session.progress;
    return (<><PageHeader title="Verifying..." subtitle={STAGE_LABELS[p.stage] ?? p.stage} /><Card className="p-10 text-center"><p className="text-sm text-muted">Still working{p.total ? ` (${p.done}/${p.total})` : ""}. This page updates automatically.</p></Card></>);
  }
  if (session.status === "failed") {
    return (<><PageHeader title="Verification failed" /><ErrorState title="This verification did not finish" message={session.error ?? "Unknown error"} />
      <div className="mt-6 flex justify-center"><Link to="/app/verify"><Button icon={Plus}>Start a new verification</Button></Link></div></>);
  }

  const FILTERS: { key: Filter; label: string; icon?: typeof CheckCircle2 }[] = [
    { key: "ALL", label: "All" }, { key: "SUPPORTED", label: "Supported", icon: CheckCircle2 },
    { key: "CONTRADICTED", label: "Contradicted", icon: XCircle }, { key: "INSUFFICIENT_EVIDENCE", label: "Insufficient", icon: CircleHelp },
    { key: "REVIEW", label: "Needs review", icon: Flag },
  ];
  const tone = sum.verdict === "contains_contradictions" ? "bad" : sum.verdict === "fully_supported" || sum.verdict === "mostly_supported" ? "info" : "warn";

  return (
    <>
      <PageHeader eyebrow={`Session ${session.id} - ${formatDate(session.created_at)}`} title="Verification results"
        subtitle={session.title ?? undefined}
        actions={<><Link to="/app/verify"><Button variant="secondary" icon={Plus}>New verification</Button></Link><Button icon={Download} loading={busy} onClick={() => void download()}>Download PDF</Button></>} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Total claims" value={sum.total_claims ?? 0} icon={ListChecks} />
        <StatCard label="Supported" value={sum.supported ?? 0} icon={CheckCircle2} tone="ok" />
        <StatCard label="Contradicted" value={sum.contradicted ?? 0} icon={XCircle} tone="bad" />
        <StatCard label="Insufficient" value={sum.insufficient ?? 0} icon={CircleHelp} tone="warn" />
        <StatCard label="Needs review" value={sum.needs_review ?? 0} icon={Flag} tone="accent" />
        <StatCard label="Processing time" value={<span className="whitespace-nowrap text-3xl">{seconds(sum.processing_time)}</span>} icon={Clock} tone="secondary" />
      </div>

      <Card className="mt-6 p-6">
        <div className="mb-4"><Notice tone={tone as "info" | "warn" | "bad"} title="Overall verification summary">{sum.overall}</Notice></div>
        <StackedBar supported={sum.supported ?? 0} contradicted={sum.contradicted ?? 0} insufficient={sum.insufficient ?? 0} />
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
          {sum.documents_used && <span className="inline-flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" />{sum.documents_used.map((d) => d.name).join(", ")}</span>}
          {sum.models?.nli && <span>NLI: <b className="text-ink">{sum.models.nli}</b></span>}
          {sum.models?.embedding_backend && <span>Dense: <b className="text-ink">{sum.models.embedding_backend}</b></span>}
        </div>
        <button onClick={() => setShowAnswer((v) => !v)} className="focus-ring mt-4 text-sm font-semibold text-secondary hover:underline">{showAnswer ? "Hide" : "Show"} original answer</button>
        {showAnswer && <p className="mt-3 whitespace-pre-wrap rounded-xl bg-sunken px-4 py-3 text-sm leading-relaxed">{session.answer_text}</p>}
      </Card>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-2xl font-semibold">Claims</h2>
        <div role="tablist" aria-label="Filter claims" className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button key={f.key} role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)}
              className={cx("focus-ring inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-semibold transition",
                filter === f.key ? "border-brand bg-brand text-brand-fg" : "border-line bg-surface text-muted hover:text-ink")}>
              {f.icon && <f.icon className="h-3.5 w-3.5" />}{f.label}<span className="tabular-nums opacity-70">{counts[f.key]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {shown.length === 0 ? (
          <EmptyState icon={ListChecks} title="No claims in this category" body="Choose another filter to see the rest." action={<Button variant="secondary" onClick={() => setFilter("ALL")}>Show all claims</Button>} />
        ) : shown.map((c, i) => (
          <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.04 }}>
            <ClaimCard claim={c} defaultOpen={claims.length <= 2} />
          </motion.div>
        ))}
      </div>
    </>
  );
}
