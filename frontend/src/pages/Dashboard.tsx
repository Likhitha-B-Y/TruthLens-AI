import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, Clock, FileStack, History as HistoryIcon, Layers, ScanSearch, Sparkles, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { Donut, Legend, StackedBar } from "../components/Charts";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, StatCard } from "../components/ui";
import { api } from "../lib/api";
import { seconds, timeAgo } from "../lib/format";
import { useAsync } from "../lib/hooks";

export default function Dashboard() {
  const o = useAsync(() => api.overview(), []);
  const d = o.data;

  return (
    <>
      <PageHeader eyebrow="Overview" title="Dashboard" subtitle="Your verification activity and evidence library at a glance."
        actions={<Link to="/app/verify"><Button icon={ScanSearch}>Quick verification</Button></Link>} />

      {o.error && !d ? <ErrorState message={o.error} onRetry={o.reload} /> : (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4 [&>*]:min-w-0">
            {!d ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />) : (<>
              <StatCard label="Verifications" value={d.completed} icon={HistoryIcon} hint={`${d.sessions} sessions in total`} />
              <StatCard label="Claims checked" value={d.claims.total_claims} icon={CheckCircle2} tone="secondary" hint={`${d.claims.needs_review} flagged for review`} />
              <StatCard label="Documents" value={d.documents} icon={FileStack} tone="accent" hint={`${d.passages} searchable passages`} />
              <StatCard label="Avg. time" value={<span className="text-3xl">{seconds(d.avg_processing_time)}</span>} icon={Clock} tone="warn" hint="per verification" />
            </>)}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] [&>*]:min-w-0">
            <Card className="p-6">
              <h2 className="font-display text-xl font-semibold">Claim distribution</h2>
              <p className="mb-5 text-sm text-muted">Across all completed verifications.</p>
              {!d ? <Skeleton className="mx-auto h-48 w-48 !rounded-full" /> : d.claims.total_claims === 0 ? (
                <EmptyState icon={Layers} title="No claims verified yet" body="Run your first verification to see how claims break down." action={<Link to="/app/verify"><Button size="sm" icon={Sparkles}>Try it now</Button></Link>} />
              ) : (
                <div className="flex flex-col items-center gap-6 sm:flex-row sm:justify-around">
                  <Donut supported={d.claims.supported} contradicted={d.claims.contradicted} insufficient={d.claims.insufficient} />
                  <div className="w-full max-w-[220px]"><Legend supported={d.claims.supported} contradicted={d.claims.contradicted} insufficient={d.claims.insufficient} /></div>
                </div>
              )}
            </Card>

            <Card className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <div><h2 className="font-display text-xl font-semibold">Recent verifications</h2><p className="text-sm text-muted">Pick up where you left off.</p></div>
                <Link to="/app/history" className="focus-ring inline-flex items-center gap-1 rounded-lg text-sm font-semibold text-secondary hover:underline">View all <ArrowRight className="h-4 w-4" /></Link>
              </div>
              {!d ? <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div> : d.recent.length === 0 ? (
                <EmptyState icon={HistoryIcon} title="Nothing here yet" body="Completed verifications appear here so you can reopen their reports." />
              ) : (
                <ul className="space-y-2.5">
                  {d.recent.map((s, i) => (
                    <motion.li key={s.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                      <Link to={`/app/results/${s.id}`} className="focus-ring group block rounded-xl border border-line px-4 py-3 transition hover:border-secondary/50 hover:bg-sunken/60">
                        <div className="flex items-center justify-between gap-3">
                          <p className="truncate text-sm font-semibold">{s.title || "Untitled"}</p>
                          {s.status === "completed" ? <span className="shrink-0 text-xs text-muted">{timeAgo(s.created_at)}</span> : <Badge tone={s.status === "failed" ? "bad" : "warn"}>{s.status}</Badge>}
                        </div>
                        {s.status === "completed" && (<div className="mt-2.5 flex items-center gap-3"><div className="flex-1"><StackedBar supported={s.summary.supported ?? 0} contradicted={s.summary.contradicted ?? 0} insufficient={s.summary.insufficient ?? 0} /></div>
                          <span className="flex shrink-0 items-center gap-1 text-xs tabular-nums text-muted"><CheckCircle2 className="h-3.5 w-3.5 text-ok" />{s.summary.supported ?? 0}<XCircle className="ml-1 h-3.5 w-3.5 text-bad" />{s.summary.contradicted ?? 0}</span></div>)}
                      </Link>
                    </motion.li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card className="mt-6 flex flex-col items-start justify-between gap-4 bg-brand p-7 text-brand-fg sm:flex-row sm:items-center">
            <div><h2 className="font-display text-2xl font-semibold">Verify a new AI answer</h2><p className="mt-1 max-w-xl text-sm text-white/75">Paste an answer, pick your trusted documents and get a claim-by-claim verdict with sources.</p></div>
            <Link to="/app/verify"><Button variant="secondary" size="lg" icon={ArrowRight} className="flex-row-reverse">Start</Button></Link>
          </Card>
        </>
      )}
    </>
  );
}
