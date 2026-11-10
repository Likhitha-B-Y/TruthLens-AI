import { motion } from "framer-motion";
import { Beaker, ClipboardCopy, Play, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, EmptyState, ErrorState, Notice, PageHeader, Skeleton, SliderField, cx } from "../components/ui";
import { api } from "../lib/api";
import { STAGE_LABELS, formatDate, num, pct, seconds } from "../lib/format";
import { useAsync, usePoll } from "../lib/hooks";
import { useToast } from "../lib/toast";
import type { EvalResults, EvalRun } from "../lib/types";

const SHORT: Record<string, string> = { bm25_keyword: "BM25 + keyword", dense_similarity: "Dense similarity", retrieval_nli: "Retrieval + NLI", proposed: "Proposed (hybrid + NLI + abstain)" };
const COLORS: Record<string, string> = { bm25_keyword: "#94a3b8", dense_similarity: "#60a5fa", retrieval_nli: "#14b8a6", proposed: "#8b5cf6" };
const RET_COLORS: Record<string, string> = { bm25: "#94a3b8", dense: "#60a5fa", hybrid: "#8b5cf6" };
const RET_NAMES: Record<string, string> = { bm25: "BM25", dense: "Dense", hybrid: "Hybrid (RRF)" };
const LABEL_SHORT: Record<string, string> = { SUPPORTED: "Supported", CONTRADICTED: "Contradicted", INSUFFICIENT_EVIDENCE: "Insufficient" };
const tip = { contentStyle: { borderRadius: 12, border: "1px solid rgb(var(--line))", background: "rgb(var(--surface))", color: "rgb(var(--ink))", fontSize: 13 } };
const axis = { tick: { fill: "rgb(var(--muted))", fontSize: 12 }, stroke: "rgb(var(--line))" };

function Code({ text }: { text: string }) {
  const toast = useToast();
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-sunken px-4 py-2.5 font-mono text-[13px]">
      <code className="overflow-x-auto whitespace-nowrap">{text}</code>
      <button aria-label="Copy command" onClick={() => { void navigator.clipboard?.writeText(text); toast.info("Copied"); }} className="focus-ring shrink-0 rounded-md p-1 text-muted hover:text-ink"><ClipboardCopy className="h-4 w-4" /></button>
    </div>
  );
}

function ChartCard({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (<Card className="p-6"><h3 className="font-display text-lg font-semibold">{title}</h3>{hint && <p className="mb-4 text-xs text-muted">{hint}</p>}<div className="mt-3 h-72">{children}</div></Card>);
}

function Heat({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const rowTotals = matrix.map((r) => r.reduce((a, b) => a + b, 0));
  return (
    <div className="overflow-x-auto">
      <div className="inline-grid min-w-[420px] grid-cols-[auto_repeat(3,minmax(88px,1fr))] gap-1.5 text-center text-sm" role="table" aria-label="Confusion matrix">
        <div />{labels.map((l) => <div key={l} className="px-1 pb-1 text-xs font-semibold text-muted">Predicted<br />{LABEL_SHORT[l]}</div>)}
        {matrix.map((row, i) => (
          <div key={i} className="contents" role="row">
            <div className="flex items-center justify-end pr-2 text-xs font-semibold text-muted">Actual {LABEL_SHORT[labels[i]]}</div>
            {row.map((v, j) => {
              const frac = rowTotals[i] ? v / rowTotals[i] : 0;
              const diag = i === j;
              return (<div key={j} role="cell" className="rounded-xl py-4" style={{ background: `rgb(${diag ? "var(--secondary)" : "var(--bad)"} / ${(0.08 + frac * 0.6).toFixed(2)})` }}>
                <p className="text-lg font-bold tabular-nums">{v}</p><p className="text-[11px] text-muted tabular-nums">{pct(frac)}</p></div>);
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function Results({ r }: { r: EvalResults }) {
  const keys = Object.keys(r.methods);
  const [cm, setCm] = useState("proposed");
  const rows = keys.map((k) => ({ key: k, name: SHORT[k], m: r.methods[k] }));
  const best = rows.reduce((a, b) => (b.m.metrics.macro_f1 > a.m.metrics.macro_f1 ? b : a));
  const f1Data = rows.map((x) => ({ name: SHORT[x.key], "Macro-F1": +x.m.metrics.macro_f1.toFixed(3), Accuracy: +x.m.metrics.accuracy.toFixed(3), key: x.key }));
  const prData = rows.map((x) => ({ name: SHORT[x.key], "Macro precision": +x.m.metrics.macro_precision.toFixed(3), "Macro recall": +x.m.metrics.macro_recall.toFixed(3) }));
  const retData = r.ks.map((k) => ({ k: `K=${k}`, ...Object.fromEntries(Object.keys(r.retrieval).map((n) => [RET_NAMES[n], +r.retrieval[n][`recall@${k}`].toFixed(3)])) }));
  const precData = r.ks.map((k) => ({ k: `K=${k}`, ...Object.fromEntries(Object.keys(r.retrieval).map((n) => [RET_NAMES[n], +r.retrieval[n][`precision@${k}`].toFixed(3)])) }));
  const timeData = rows.map((x) => ({ name: SHORT[x.key], Retrieval: +(x.m.timing.retrieval_s_per_claim * 1000).toFixed(1), NLI: +(x.m.timing.nli_s_per_claim * 1000).toFixed(1) }));
  const absData = rows.map((x) => ({ name: SHORT[x.key], Coverage: +x.m.abstention.coverage.toFixed(3), "Error on answered": x.m.abstention.selective_error_rate == null ? 0 : +x.m.abstention.selective_error_rate.toFixed(3) }));
  const sel = r.methods[cm];

  return (
    <>
      <Card className="mb-6 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow mb-1">Latest run - {formatDate(r.generated_at)}</p>
            <h2 className="font-display text-2xl font-semibold">Best macro-F1: <span className="text-accent">{best.name}</span> at {num(best.m.metrics.macro_f1)}</h2></div>
          <div className="flex flex-wrap gap-2 text-xs"><Badge tone="neutral">{r.dataset.test.n} test claims</Badge><Badge tone="neutral">{r.dataset.calibration.n} calibration</Badge><Badge tone="neutral">{r.dataset.corpus.pages} pages / {r.dataset.corpus.passages} passages</Badge><Badge tone="neutral">{seconds(r.total_seconds)}</Badge></div>
        </div>
        <p className="mt-3 text-sm text-muted">NLI <b className="text-ink">{r.models.nli}</b> &middot; embeddings <b className="text-ink">{r.models.embedding}</b> &middot; device {r.models.device}</p>
        <div className="mt-4 space-y-2">{r.notes.map((n, i) => <Notice key={i} tone={n.startsWith("WARNING") ? "warn" : "info"}>{n}</Notice>)}</div>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-line px-6 py-4"><h3 className="font-display text-lg font-semibold">Baseline comparison</h3><p className="text-xs text-muted">Test split only. Thresholds were tuned on the calibration split.</p></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-sunken/60 text-xs uppercase tracking-wider text-muted"><tr>
              {["Method", "Accuracy", "Macro-F1", "Precision", "Recall", "Coverage", "Err. on answered", "Citation correct", "Time / claim"].map((h) => <th key={h} className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.key} className={cx("border-t border-line", x.key === "proposed" && "bg-accent/5")}>
                  <td className="px-4 py-3.5 font-semibold"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: COLORS[x.key] }} />{x.name}</td>
                  <td className="px-4 tabular-nums">{pct(x.m.metrics.accuracy, 1)}</td>
                  <td className="px-4 font-semibold tabular-nums">{num(x.m.metrics.macro_f1)}</td>
                  <td className="px-4 tabular-nums">{num(x.m.metrics.macro_precision)}</td>
                  <td className="px-4 tabular-nums">{num(x.m.metrics.macro_recall)}</td>
                  <td className="px-4 tabular-nums">{pct(x.m.abstention.coverage, 1)}</td>
                  <td className="px-4 tabular-nums">{pct(x.m.abstention.selective_error_rate, 1)}</td>
                  <td className="px-4 tabular-nums">{pct(x.m.citation.citation_correctness, 1)}</td>
                  <td className="px-4 tabular-nums">{seconds(x.m.timing.total_s_per_claim)}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard title="Macro-F1 and accuracy" hint="Higher is better. Macro-F1 weights the three classes equally.">
          <ResponsiveContainer><BarChart data={f1Data} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tickFormatter={(v: string) => v.split(" (")[0].replace("Dense similarity", "Dense").replace("BM25 + keyword", "BM25+kw").replace("Retrieval + NLI", "Retr.+NLI")} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
            <Bar dataKey="Macro-F1" fill="#8b5cf6" radius={[6, 6, 0, 0]} /><Bar dataKey="Accuracy" fill="#14b8a6" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Macro precision and recall">
          <ResponsiveContainer><BarChart data={prData} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tickFormatter={(v: string) => v.split(" (")[0].replace("Dense similarity", "Dense").replace("BM25 + keyword", "BM25+kw").replace("Retrieval + NLI", "Retr.+NLI")} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
            <Bar dataKey="Macro precision" fill="#60a5fa" radius={[6, 6, 0, 0]} /><Bar dataKey="Macro recall" fill="#f59e0b" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Evidence Recall@K" hint={`Verifiable claims whose gold evidence is fully inside the top K passages (n=${r.retrieval.hybrid?.n_verifiable}).`}>
          <ResponsiveContainer><LineChart data={retData} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" /><XAxis dataKey="k" {...axis} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
            {Object.keys(r.retrieval).map((n) => <Line key={n} type="monotone" dataKey={RET_NAMES[n]} stroke={RET_COLORS[n]} strokeWidth={n === "hybrid" ? 3 : 2} dot={{ r: 4 }} />)}</LineChart></ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Evidence Precision@K" hint="Share of the top K passages that contain a gold evidence sentence.">
          <ResponsiveContainer><LineChart data={precData} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" /><XAxis dataKey="k" {...axis} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
            {Object.keys(r.retrieval).map((n) => <Line key={n} type="monotone" dataKey={RET_NAMES[n]} stroke={RET_COLORS[n]} strokeWidth={n === "hybrid" ? 3 : 2} dot={{ r: 4 }} />)}</LineChart></ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Abstention behaviour" hint="Coverage = share of claims given a definite verdict. Error is measured only on those.">
          <ResponsiveContainer><BarChart data={absData} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tickFormatter={(v: string) => v.split(" (")[0].replace("Dense similarity", "Dense").replace("BM25 + keyword", "BM25+kw").replace("Retrieval + NLI", "Retr.+NLI")} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
            <Bar dataKey="Coverage" fill="#14b8a6" radius={[6, 6, 0, 0]} /><Bar dataKey="Error on answered" fill="#ef4444" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Processing time per claim (ms)" hint="Measured on this machine. NLI dominates on CPU.">
          <ResponsiveContainer><BarChart data={timeData} margin={{ left: -10 }}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tickFormatter={(v: string) => v.split(" (")[0].replace("Dense similarity", "Dense").replace("BM25 + keyword", "BM25+kw").replace("Retrieval + NLI", "Retr.+NLI")} /><YAxis {...axis} /><Tooltip {...tip} /><Legend />
            <Bar stackId="t" dataKey="Retrieval" fill="#60a5fa" /><Bar stackId="t" dataKey="NLI" fill="#8b5cf6" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-6 p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h3 className="font-display text-lg font-semibold">Confusion matrix and per-class scores</h3>
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Choose method">{keys.map((k) => (
            <button key={k} role="tab" aria-selected={cm === k} onClick={() => setCm(k)} className={cx("focus-ring rounded-full border px-3 py-1 text-sm font-semibold transition", cm === k ? "border-brand bg-brand text-brand-fg" : "border-line text-muted hover:text-ink")}>{SHORT[k].split(" (")[0]}</button>))}</div></div>
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <Heat labels={sel.metrics.confusion_matrix.labels} matrix={sel.metrics.confusion_matrix.matrix} />
          <table className="h-fit w-full text-sm"><thead className="text-xs uppercase tracking-wider text-muted"><tr><th className="py-2 text-left">Class</th><th>Prec.</th><th>Recall</th><th>F1</th><th>n</th></tr></thead>
            <tbody>{Object.entries(sel.metrics.per_class).map(([k, v]) => (<tr key={k} className="border-t border-line text-center"><td className="py-2.5 text-left font-semibold">{LABEL_SHORT[k]}</td><td className="tabular-nums">{num(v.precision, 2)}</td><td className="tabular-nums">{num(v.recall, 2)}</td><td className="tabular-nums">{num(v.f1, 2)}</td><td className="tabular-nums text-muted">{v.support}</td></tr>))}</tbody></table>
        </div>
        <p className="mt-4 text-xs text-muted">Thresholds used: {Object.entries(sel.thresholds).map(([k, v]) => `${k.replace(/_/g, " ")} = ${v}`).join(", ") || "none (argmax rule)"}{sel.tuned_on_calibration ? " (tuned on calibration split)" : ""}. Abstain precision {pct(sel.abstention.abstain_precision)}, abstain recall {pct(sel.abstention.abstain_recall)}, FEVER-style score {pct(sel.citation.fever_style_score, 1)}.</p>
      </Card>
    </>
  );
}

function RunForm({ onStarted, disabled }: { onStarted: (r: EvalRun) => void; disabled?: boolean }) {
  const toast = useToast();
  const [n, setN] = useState(150);
  const [k, setK] = useState(5);
  const [dis, setDis] = useState(300);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { onStarted(await api.evalRun({ sample_size: n, top_k: k, distractors: dis })); toast.info("Evaluation started", "This can take several minutes on CPU."); }
    catch (e) { toast.error("Could not start the evaluation", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card className="p-6">
      <h3 className="font-display text-lg font-semibold">Run a FEVER evaluation</h3>
      <p className="mb-3 text-sm text-muted">Use a smaller subset on limited hardware. Claims are balanced across the three labels.</p>
      <div className="grid gap-x-8 sm:grid-cols-3">
        <SliderField label="Claims" value={n} min={30} max={600} step={3} onChange={setN} hint="Total, split 1/3 per label." />
        <SliderField label="Top-K evidence" value={k} min={1} max={10} step={1} onChange={setK} />
        <SliderField label="Distractor pages" value={dis} min={0} max={2000} step={50} onChange={setDis} hint="Extra random Wikipedia pages." />
      </div>
      <div className="mt-4"><Button icon={Play} loading={busy} disabled={disabled} onClick={() => void run()}>Run evaluation</Button></div>
    </Card>
  );
}

export default function Evaluation() {
  const st = useAsync(() => api.evalStatus(), []);
  const [live, setLive] = useState<EvalRun | null>(null);
  const running = live ?? st.data?.running ?? null;
  const isRunning = running?.status === "running";
  usePoll(async () => {
    if (!running) return;
    const r = await api.evalRunGet(running.id);
    setLive(r);
    if (r.status !== "running") { st.reload(); }
  }, 2000, !!isRunning);

  const results = (live?.status === "completed" ? live.results : null) ?? st.data?.latest?.results ?? null;
  const failed = live?.status === "failed" ? live : null;
  const p = running?.progress;

  return (
    <>
      <PageHeader eyebrow="Research" title="Evaluation" subtitle="Four systems compared on a FEVER subset with real metrics: nothing here is hard-coded, every number comes from an evaluation run on your machine."
        actions={<Badge tone="secondary"><Beaker className="h-3.5 w-3.5" />FEVER</Badge>} />

      {st.loading && !st.data ? <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>
        : st.error && !st.data ? <ErrorState message={st.error} onRetry={st.reload} />
        : (<>
          {failed && <div className="mb-6"><ErrorState title="The evaluation failed" message={failed.error ?? "Unknown error"} /></div>}
          {isRunning && p && (
            <Card className="mb-6 p-6"><p className="text-sm font-semibold">{STAGE_LABELS[p.stage] ?? p.stage}{p.total > 0 ? ` - ${p.done}/${p.total}` : "..."}</p>
              <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-sunken"><motion.div className="h-full rounded-full bg-accent" animate={{ width: p.total ? `${(p.done / p.total) * 100}%` : "8%" }} /></div>
              <p className="mt-3 text-xs text-muted">Running in the background. You can leave this page; results appear here when finished.</p></Card>)}

          {results ? (<>
            <Results r={results} />
            {st.data?.data.ready && <div className="mt-6"><RunForm onStarted={setLive} disabled={isRunning} /></div>}
          </>) : st.data && !st.data.data.ready ? (
            <Card className="p-6 sm:p-8">
              <EmptyState icon={TriangleAlert} title="No evaluation results yet" body="The FEVER dataset has to be downloaded once. It is too large to ship inside the project, so evaluation needs a one-time setup on your machine." />
              <div className="mx-auto mt-6 max-w-2xl space-y-3 text-sm">
                <p className="font-semibold">1. Download the data (claims are small; Wikipedia is about 1.7 GB)</p><Code text={st.data.setup_hint} />
                <p className="pt-2 font-semibold">2. Then run it from a terminal (or from this page once the data exists)</p><Code text="python evaluation/run_fever_eval.py --sample-size 150" />
                <p className="text-xs text-muted">Detected data folder: {st.data.data.data_dir}. See evaluation/README.md for manual download and low-memory options.</p>
              </div>
            </Card>
          ) : st.data ? (<RunForm onStarted={setLive} disabled={isRunning} />) : null}
        </>)}
    </>
  );
}
