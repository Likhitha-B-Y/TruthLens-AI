import { motion } from "framer-motion";
import { ArrowUpRight, CheckCircle2, CircleHelp, Flag, History as HistoryIcon, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { StackedBar } from "../components/Charts";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, PageHeader, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, seconds } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useToast } from "../lib/toast";
import type { Session } from "../lib/types";

export default function HistoryPage() {
  const toast = useToast();
  const h = useAsync(() => api.history(), []);
  const [del, setDel] = useState<Session | null>(null);
  const [clearAll, setClearAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const sessions = h.data?.sessions ?? [];

  const remove = async () => {
    if (!del) return;
    setBusy(true);
    try { await api.deleteSession(del.id); toast.success("Verification deleted"); setDel(null); h.reload(); }
    catch (e) { toast.error("Delete failed", (e as Error).message); } finally { setBusy(false); }
  };
  const clear = async () => {
    setBusy(true);
    try { const r = await api.clearHistory(); toast.success(`Deleted ${r.deleted} verification${r.deleted === 1 ? "" : "s"}`); setClearAll(false); h.reload(); }
    catch (e) { toast.error("Could not clear history", (e as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader eyebrow="Archive" title="Verification history" subtitle="Every verification is saved locally so you can reopen the report and download the PDF again."
        actions={sessions.length > 0 ? <Button variant="danger" icon={Trash2} onClick={() => setClearAll(true)}>Delete all</Button> : undefined} />
      {h.loading && !h.data ? <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
        : h.error && !h.data ? <ErrorState message={h.error} onRetry={h.reload} />
        : sessions.length === 0 ? <EmptyState icon={HistoryIcon} title="No verifications yet" body="Your completed verifications will be listed here with dates and summaries." action={<Link to="/app/verify"><Button>Start your first verification</Button></Link>} />
        : (
          <ul className="space-y-3">
            {sessions.map((s, i) => {
              const sm = s.summary;
              const done = s.status === "completed";
              return (
                <motion.li key={s.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }}>
                  <Card className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-[15px] font-semibold">{s.title || "Untitled"}</h3>
                          {!done && <Badge tone={s.status === "failed" ? "bad" : "warn"}>{s.status}</Badge>}
                        </div>
                        <p className="mt-0.5 text-xs text-muted">{formatDate(s.created_at)} &middot; ID {s.id}{done && s.processing_time ? ` \u00b7 ${seconds(s.processing_time)}` : ""}</p>
                        {s.status === "failed" && s.error && <p className="mt-2 text-sm text-bad">{s.error}</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        {done && <Link to={`/app/results/${s.id}`}><Button size="sm" icon={ArrowUpRight}>Open report</Button></Link>}
                        <button onClick={() => setDel(s)} aria-label="Delete verification" className="focus-ring rounded-lg p-2 text-muted hover:bg-bad-bg/50 hover:text-bad"><Trash2 className="h-4 w-4" /></button>
                      </div>
                    </div>
                    {done && (
                      <div className="mt-4">
                        <StackedBar supported={sm.supported ?? 0} contradicted={sm.contradicted ?? 0} insufficient={sm.insufficient ?? 0} />
                        <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
                          <span><b className="tabular-nums text-ink">{sm.total_claims ?? 0}</b> claims</span>
                          <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-ok" /><b className="tabular-nums text-ink">{sm.supported ?? 0}</b> supported</span>
                          <span className="inline-flex items-center gap-1"><XCircle className="h-3.5 w-3.5 text-bad" /><b className="tabular-nums text-ink">{sm.contradicted ?? 0}</b> contradicted</span>
                          <span className="inline-flex items-center gap-1"><CircleHelp className="h-3.5 w-3.5 text-warn" /><b className="tabular-nums text-ink">{sm.insufficient ?? 0}</b> insufficient</span>
                          {(sm.needs_review ?? 0) > 0 && <span className="inline-flex items-center gap-1"><Flag className="h-3.5 w-3.5 text-accent" /><b className="tabular-nums text-ink">{sm.needs_review}</b> need review</span>}
                        </div>
                        {s.answer_preview && <p className="mt-3 line-clamp-2 text-sm text-muted">{s.answer_preview}</p>}
                      </div>
                    )}
                  </Card>
                </motion.li>
              );
            })}
          </ul>
        )}
      <ConfirmDialog open={!!del} busy={busy} onClose={() => setDel(null)} onConfirm={() => void remove()} title="Delete this verification?" body="The saved results and its PDF report will be removed. This cannot be undone." />
      <ConfirmDialog open={clearAll} busy={busy} onClose={() => setClearAll(false)} onConfirm={() => void clear()} title="Delete all history?" confirmLabel="Delete all" body={`All ${sessions.length} saved verifications will be permanently removed.`} />
    </>
  );
}
