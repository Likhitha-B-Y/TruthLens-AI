import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, FileText, Flag, Layers, Scale } from "lucide-react";
import { useState } from "react";
import { REVIEW_REASONS, STATUS_META, num, pct } from "../lib/format";
import type { ClaimResult, Evidence } from "../lib/types";
import { Badge, ScoreBar, StatusBadge, cx } from "./ui";

const REL = {
  supports: { label: "Supports claim", tone: "ok" as const },
  contradicts: { label: "Contradicts claim", tone: "bad" as const },
  neutral: { label: "Neutral", tone: "neutral" as const },
};

function EvidenceBlock({ e, index, highlight }: { e: Evidence; index: number; highlight?: boolean }) {
  const rel = REL[e.relation];
  return (
    <div className={cx("rounded-xl border p-4", highlight ? "border-secondary/40 bg-secondary/5" : "border-line bg-sunken/50")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-surface text-xs font-bold shadow-sm">{index}</span>
        <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold"><FileText className="h-4 w-4 shrink-0 text-muted" /><span className="truncate">{e.doc_name}</span></span>
        <Badge tone="neutral">Page {e.page}</Badge>
        <Badge tone={rel.tone}>{rel.label}</Badge>
      </div>
      <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm leading-relaxed text-ink/90">{e.text}</blockquote>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
        <div><dt className="text-muted">NLI entail / contra / neutral</dt><dd className="font-semibold tabular-nums">{pct(e.nli.entailment)} / {pct(e.nli.contradiction)} / {pct(e.nli.neutral)}</dd></div>
        <div><dt className="text-muted">BM25 score{e.bm25_rank ? ` (rank ${e.bm25_rank})` : ""}</dt><dd className="font-semibold tabular-nums">{num(e.bm25_score, 2)}</dd></div>
        <div><dt className="text-muted">Dense similarity{e.dense_rank ? ` (rank ${e.dense_rank})` : ""}</dt><dd className="font-semibold tabular-nums">{num(e.dense_score, 3)}</dd></div>
        <div><dt className="text-muted">Fused retrieval score</dt><dd className="font-semibold tabular-nums">{num(e.fused_score, 4)}</dd></div>
      </dl>
    </div>
  );
}

export default function ClaimCard({ claim, defaultOpen = false }: { claim: ClaimResult; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [more, setMore] = useState(false);
  const m = STATUS_META[claim.status];
  const primary = claim.evidence.filter((e) => e.primary);
  const others = claim.evidence.filter((e) => !e.primary);
  const shownPrimary = primary.length ? primary : claim.evidence.slice(0, 1);
  const rest = primary.length ? others : claim.evidence.slice(1);

  return (
    <motion.article layout="position" className={cx("card overflow-hidden border-l-4", claim.status === "SUPPORTED" ? "border-l-ok" : claim.status === "CONTRADICTED" ? "border-l-bad" : "border-l-warn")}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="focus-ring flex w-full items-start gap-4 p-5 text-left">
        <span className="mt-0.5 rounded-lg bg-sunken px-2 py-1 text-xs font-bold tabular-nums text-muted">{claim.id}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold leading-snug">{claim.text}</span>
          <span className="mt-2.5 flex flex-wrap items-center gap-2">
            <StatusBadge status={claim.status} size="sm" />
            {claim.conflict && <Badge tone="warn"><Scale className="h-3 w-3" />Conflicting sources</Badge>}
            {claim.needs_review && <Badge tone="accent"><Flag className="h-3 w-3" />Needs human review</Badge>}
            <span className="text-xs text-muted">Confidence <b className="tabular-nums text-ink">{pct(claim.confidence)}</b></span>
          </span>
        </span>
        <ChevronDown className={cx("mt-1 h-5 w-5 shrink-0 text-muted transition-transform", open && "rotate-180")} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25 }} className="overflow-hidden">
            <div className="space-y-5 border-t border-line px-5 pb-5 pt-5">
              <div className={cx("rounded-xl px-4 py-3 text-sm leading-relaxed", m.bg)}>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Why this verdict</p>
                {claim.explanation}
              </div>

              {claim.needs_review && claim.review_reasons.length > 0 && (
                <div className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm">
                  <Flag className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <div><b>Please review manually.</b> {claim.review_reasons.map((r) => REVIEW_REASONS[r] ?? r).join(" ")}</div>
                </div>
              )}

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">NLI scores for the decisive evidence</p>
                <div className="grid gap-3 sm:grid-cols-3">
                  <ScoreBar label="Entailment" value={claim.scores.entailment} tone="ok" />
                  <ScoreBar label="Contradiction" value={claim.scores.contradiction} tone="bad" />
                  <ScoreBar label="Neutral" value={claim.scores.neutral} tone="warn" />
                </div>
              </div>

              {claim.sentence && claim.sentence !== claim.text && (
                <div className="text-sm"><p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Original sentence</p><p className="italic text-muted">&ldquo;{claim.sentence}&rdquo;</p>
                  {claim.context_note && <p className="mt-1 text-xs text-muted">{claim.context_note}.</p>}</div>
              )}

              <div>
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><Layers className="h-3.5 w-3.5" />{claim.conflict ? "Conflicting evidence" : "Evidence"}</p>
                {claim.evidence.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-line px-4 py-5 text-center text-sm text-muted">No passage was retrieved for this claim.</p>
                ) : (
                  <div className="space-y-3">
                    {shownPrimary.map((e, i) => <EvidenceBlock key={e.passage_id} e={e} index={i + 1} highlight />)}
                    {rest.length > 0 && (
                      <>
                        <button onClick={() => setMore((v) => !v)} className="focus-ring text-sm font-semibold text-secondary hover:underline">
                          {more ? "Hide" : "Show"} {rest.length} additional evidence passage{rest.length > 1 ? "s" : ""}
                        </button>
                        {more && rest.map((e, i) => <EvidenceBlock key={e.passage_id} e={e} index={shownPrimary.length + i + 1} />)}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
