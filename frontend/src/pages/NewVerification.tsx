import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCheck, FileText, FileUp, Info, Plus, ScanSearch, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorState, Notice, PageHeader, Skeleton, Spinner, cx } from "../components/ui";
import { api } from "../lib/api";
import { STAGE_LABELS, formatBytes } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useModelStatus } from "../lib/modelStatus";
import { useToast } from "../lib/toast";
import type { ExtractedClaim, SampleAnswer, Session } from "../lib/types";

const MAX_CHARS = 30000;

function RunProgress({ session }: { session: Session }) {
  const p = session.progress;
  const frac = p.total > 0 ? Math.min(1, p.done / p.total) : 0;
  return (
    <Card className="p-8">
      <div className="mx-auto max-w-md text-center">
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2.4, ease: "linear" }} className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-secondary/10 text-secondary">
          <ScanSearch className="h-7 w-7" />
        </motion.div>
        <h2 className="mt-5 font-display text-2xl font-semibold">Verifying your answer</h2>
        <p className="mt-1.5 text-sm text-muted">{STAGE_LABELS[p.stage] ?? p.stage}{p.total > 0 ? ` - ${p.done} of ${p.total}` : "..."}</p>
        <div className="mt-6 h-2.5 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={Math.round(frac * 100)} aria-valuemin={0} aria-valuemax={100}>
          <motion.div className="h-full rounded-full bg-secondary" animate={{ width: p.total > 0 ? `${frac * 100}%` : "12%" }} transition={{ duration: 0.4 }} />
        </div>
        <p className="mt-4 text-xs text-muted">The first run on CPU can take a minute while the models warm up.</p>
      </div>
    </Card>
  );
}

export default function NewVerification() {
  const nav = useNavigate();
  const toast = useToast();
  const { status } = useModelStatus();
  const docs = useAsync(() => api.documents(), []);
  const samples = useAsync(() => api.samples(), []);

  const [answer, setAnswer] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [claims, setClaims] = useState<ExtractedClaim[] | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [run, setRun] = useState<Session | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [loadingSamples, setLoadingSamples] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout>>();
  const seenDocs = useRef(false);

  const documents = docs.data?.documents ?? [];
  // select every document by default the first time the library loads
  useEffect(() => {
    if (docs.data && !seenDocs.current) { seenDocs.current = true; setSelected(new Set(docs.data.documents.map((d) => d.id))); }
  }, [docs.data]);
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  const nliReady = status?.nli.state === "ready";
  const chars = answer.length;
  const canRun = answer.trim().length > 0 && selected.size > 0 && chars <= MAX_CHARS;

  const addFiles = useCallback(async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    try {
      const r = await api.upload(files);
      const newIds: number[] = [];
      r.results.forEach((x) => {
        if (x.ok && x.document) { newIds.push(x.document.id); if (x.duplicate) toast.info(`${x.filename} is already in the library`); }
        else toast.error(`Could not add ${x.filename}`, x.error);
      });
      if (r.uploaded) toast.success(`Added ${r.uploaded} document${r.uploaded > 1 ? "s" : ""}`, "Indexes are rebuilding in the background.");
      docs.reload();
      setSelected((s) => new Set([...s, ...newIds]));
    } catch (e) { toast.error("Upload failed", (e as Error).message); }
    finally { setUploading(false); }
  }, [docs, toast]);

  const loadSample = async (a?: SampleAnswer) => {
    setLoadingSamples(true);
    try {
      const r = await api.loadSamples();
      const d = await api.documents();
      docs.setData(d);
      setSelected(new Set(d.documents.map((x) => x.id)));
      const pick = a ?? samples.data?.answers[0];
      if (pick) { setAnswer(pick.answer); setClaims(null); }
      toast.success(r.loaded.length ? "Sample documents loaded" : "Sample answer loaded", r.loaded.length ? `${r.loaded.length} reference documents added to your library.` : undefined);
    } catch (e) { toast.error("Could not load samples", (e as Error).message); }
    finally { setLoadingSamples(false); }
  };

  const extract = async () => {
    setExtracting(true);
    try {
      const r = await api.extractClaims(answer);
      if (r.count === 0) toast.info("No checkable claims found", "Try a longer answer made of factual statements.");
      setClaims(r.claims);
    } catch (e) { toast.error("Claim extraction failed", (e as Error).message); }
    finally { setExtracting(false); }
  };

  const poll = (id: string) => {
    api.session(id).then((s) => {
      setRun(s);
      if (s.status === "completed") { toast.success("Verification complete"); nav(`/app/results/${id}`); }
      else if (s.status === "failed") setRunError(s.error ?? "Verification failed.");
      else pollRef.current = setTimeout(() => poll(id), 600);
    }).catch((e: Error) => setRunError(e.message));
  };

  const start = async (useClaims: boolean) => {
    setRunError(null);
    try {
      const body = { answer, document_ids: [...selected], claims: useClaims && claims ? claims.filter((c) => c.text.trim()) : undefined };
      const s = await api.verify(body);
      setRun(s);
      poll(s.id);
    } catch (e) { setRunError((e as Error).message); setRun(null); }
  };

  const updateClaim = (i: number, text: string) => setClaims((c) => c && c.map((x, k) => (k === i ? { ...x, text, source: "user" } : x)));
  const removeClaim = (i: number) => setClaims((c) => c && c.filter((_, k) => k !== i));
  const addClaim = () => setClaims((c) => [...(c ?? []), { id: `C${(c?.length ?? 0) + 1}`, text: "", sentence: "", sentence_id: 0, order: (c?.length ?? 0) + 1, source: "user", resolved_pronoun: false, context_note: "" }]);

  const running = run && (run.status === "queued" || run.status === "running");
  const allSelected = useMemo(() => documents.length > 0 && documents.every((d) => selected.has(d.id)), [documents, selected]);

  if (running && run) return (<><PageHeader eyebrow="New verification" title="Working on it" /><RunProgress session={run} /></>);

  return (
    <>
      <PageHeader eyebrow="New verification" title="Check an AI answer against your documents"
        subtitle="Paste the answer, choose the trusted documents to verify it against, then let TruthLens check every claim." />

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {[["1", "Paste the AI answer"], ["2", "Pick trusted documents"], ["3", "Verify and review"]].map(([n, t]) => (
          <div key={n} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3"><span className="grid h-7 w-7 place-items-center rounded-lg bg-brand text-xs font-bold text-brand-fg">{n}</span><span className="text-sm font-semibold">{t}</span></div>
        ))}
      </div>

      {runError && <div className="mb-6"><ErrorState title="Verification could not finish" message={runError} onRetry={() => setRunError(null)} /></div>}
      {status && !nliReady && (
        <div className="mb-6"><Notice tone={status.nli.state === "error" ? "bad" : "warn"} title={status.nli.state === "loading" ? "The NLI model is still loading" : "The NLI model is not available"}>
          {status.nli.message || "Please wait a moment."} {status.nli.state === "error" && <>See <Link to="/app/settings" className="font-semibold underline">Settings</Link> for how to fix it.</>}
        </Notice></div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* -------- left: answer + claims */}
        <div className="space-y-6">
          <Card className="p-5 sm:p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="answer" className="text-sm font-bold">AI-generated answer</label>
              <div className="flex flex-wrap items-center gap-2">
                {(samples.data?.answers ?? []).map((a) => (
                  <button key={a.id} onClick={() => void loadSample(a)} disabled={loadingSamples} className="focus-ring rounded-full border border-line bg-sunken px-3 py-1 text-xs font-semibold text-muted transition hover:text-ink disabled:opacity-50">
                    <Sparkles className="mr-1 inline h-3 w-3" />{a.title.split(" (")[0]}
                  </button>
                ))}
              </div>
            </div>
            <textarea id="answer" value={answer} onChange={(e) => { setAnswer(e.target.value); setClaims(null); }} rows={13} spellCheck={false}
              placeholder="Paste the answer you want to verify here, for example a paragraph from a chatbot..."
              className="input min-h-[280px] resize-y font-sans text-[15px] leading-relaxed" />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <span className={cx("text-xs tabular-nums", chars > MAX_CHARS ? "font-semibold text-bad" : "text-muted")}>{chars.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters</span>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" icon={Wand2} loading={extracting} disabled={!answer.trim()} onClick={() => void extract()}>Review claims first</Button>
                <Button icon={ScanSearch} disabled={!canRun} onClick={() => void start(false)} title={!selected.size ? "Select at least one document" : undefined}>Verify answer</Button>
              </div>
            </div>
          </Card>

          <AnimatePresence>
            {claims && (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <Card className="p-5 sm:p-6">
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
                    <h2 className="font-display text-xl font-semibold">Extracted claims <Badge tone="secondary" className="ml-1.5 align-middle">{claims.length}</Badge></h2>
                    <Button size="sm" variant="secondary" icon={Plus} onClick={addClaim}>Add claim</Button>
                  </div>
                  <p className="mb-4 text-sm text-muted">Edit, remove or add claims. Automatic splitting is heuristic, so fix anything that looks off before verifying.</p>
                  {claims.length === 0 ? (
                    <EmptyState icon={Info} title="No checkable claims found" body="Questions and chit-chat are skipped. Add a claim manually or paste a more factual answer." />
                  ) : (
                    <ul className="space-y-2.5">
                      {claims.map((c, i) => (
                        <li key={`${c.id}-${i}`} className="group flex items-start gap-2.5">
                          <span className="mt-2.5 w-9 shrink-0 text-xs font-bold tabular-nums text-muted">{c.id}</span>
                          <div className="min-w-0 flex-1">
                            <input value={c.text} onChange={(e) => updateClaim(i, e.target.value)} className="input" aria-label={`Claim ${c.id}`} placeholder="Type a factual claim..." />
                            {c.resolved_pronoun && <p className="mt-1 text-xs text-secondary">Pronoun resolved from the previous sentence</p>}
                            {c.sentence && c.sentence !== c.text && <p className="mt-1 truncate text-xs text-muted" title={c.sentence}>From: {c.sentence}</p>}
                          </div>
                          <button onClick={() => removeClaim(i)} aria-label={`Remove claim ${c.id}`} className="focus-ring mt-1.5 rounded-lg p-2 text-muted hover:bg-bad-bg/50 hover:text-bad"><Trash2 className="h-4 w-4" /></button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-5 flex justify-end">
                    <Button icon={CheckCheck} disabled={!selected.size || !claims.some((c) => c.text.trim())} onClick={() => void start(true)}>
                      Verify {claims.filter((c) => c.text.trim()).length} claim{claims.filter((c) => c.text.trim()).length === 1 ? "" : "s"}
                    </Button>
                  </div>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* -------- right: documents */}
        <div className="space-y-6">
          <Card className="p-5 sm:p-6">
            <h2 className="mb-1 font-display text-xl font-semibold">Trusted documents</h2>
            <p className="mb-4 text-sm text-muted">PDF, DOCX or TXT. Claims are checked only against the documents you select.</p>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(Array.from(e.dataTransfer.files)); }}
              onClick={() => fileRef.current?.click()} role="button" tabIndex={0} aria-label="Upload documents"
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileRef.current?.click()}
              className={cx("focus-ring cursor-pointer rounded-2xl border-2 border-dashed px-5 py-8 text-center transition", dragging ? "border-accent bg-accent/5" : "border-line hover:border-secondary/60 hover:bg-sunken/60")}>
              {uploading ? <Spinner className="mx-auto h-6 w-6" /> : <FileUp className="mx-auto h-7 w-7 text-secondary" />}
              <p className="mt-2 text-sm font-semibold">{uploading ? "Uploading and processing..." : "Drag and drop files here"}</p>
              <p className="mt-0.5 text-xs text-muted">or click to browse &middot; up to 25 MB each</p>
              <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt" className="hidden" aria-hidden="true"
                onChange={(e) => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </div>

            <div className="mt-5">
              {docs.loading && !docs.data ? <div className="space-y-2"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
                : docs.error ? <ErrorState message={docs.error} onRetry={docs.reload} />
                : documents.length === 0 ? (
                  <div className="rounded-xl bg-sunken px-4 py-5 text-center text-sm text-muted">
                    <p>No documents yet.</p>
                    <Button size="sm" variant="secondary" className="mt-3" icon={Sparkles} loading={loadingSamples} onClick={() => void loadSample()}>Load sample documents</Button>
                  </div>
                ) : (
                  <>
                    <div className="mb-2 flex items-center justify-between text-xs">
                      <span className="font-semibold text-muted">{selected.size} of {documents.length} selected</span>
                      <button className="focus-ring font-semibold text-secondary hover:underline" onClick={() => setSelected(allSelected ? new Set() : new Set(documents.map((d) => d.id)))}>{allSelected ? "Clear" : "Select all"}</button>
                    </div>
                    <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
                      {documents.map((d) => {
                        const on = selected.has(d.id);
                        return (
                          <li key={d.id}>
                            <label className={cx("flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-2.5 transition", on ? "border-secondary/50 bg-secondary/5" : "border-line hover:bg-sunken/60")}>
                              <input type="checkbox" checked={on} className="h-4 w-4 accent-[rgb(var(--secondary))]"
                                onChange={() => setSelected((s) => { const n = new Set(s); if (n.has(d.id)) n.delete(d.id); else n.add(d.id); return n; })} />
                              <FileText className="h-4 w-4 shrink-0 text-muted" />
                              <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{d.name}</span>
                                <span className="text-xs text-muted">{d.page_count} page{d.page_count > 1 ? "s" : ""} &middot; {d.passage_count} passages &middot; {formatBytes(d.size_bytes)}</span></span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
            </div>
            {documents.length > 0 && selected.size === 0 && (
              <p className="mt-3 flex items-center gap-2 text-xs font-medium text-warn"><AlertTriangle className="h-4 w-4" />Select at least one document to verify against.</p>
            )}
          </Card>

          <Card className="bg-sunken/60 p-5 text-sm leading-relaxed text-muted shadow-none">
            <p className="mb-1.5 font-bold text-ink">How verdicts are decided</p>
            Retrieval finds the most relevant passages. A natural-language-inference model then reads each passage and the claim and
            judges whether the passage <b className="text-ok">entails</b>, <b className="text-bad">contradicts</b> or is <b className="text-warn">neutral</b> to it.
            Similarity alone never decides a verdict.
          </Card>
        </div>
      </div>
    </>
  );
}
