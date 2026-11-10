import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Database, FileText, FileUp, Library as LibIcon, RefreshCw, Search, Sparkles, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, PageHeader, Skeleton, Spinner, cx } from "../components/ui";
import { api } from "../lib/api";
import { formatBytes, formatDate } from "../lib/format";
import { useAsync, useDebounced, usePoll } from "../lib/hooks";
import { useToast } from "../lib/toast";
import type { DocumentInfo } from "../lib/types";

const EXTS = [{ v: "", l: "All" }, { v: "pdf", l: "PDF" }, { v: "docx", l: "DOCX" }, { v: "txt", l: "TXT" }];

function DocCard({ d, onDelete }: { d: DocumentInfo; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  const detail = useAsync(() => (open ? api.document(d.id) : Promise.resolve(null)), [open, d.id]);
  return (
    <Card className="overflow-hidden">
      <div className="flex items-start gap-4 p-5">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-secondary/10 text-secondary"><FileText className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><h3 className="truncate text-[15px] font-semibold">{d.name}</h3><Badge tone="neutral">{d.ext.slice(1).toUpperCase()}</Badge>{d.is_sample && <Badge tone="accent">Sample</Badge>}</div>
          {(d.meta.title || d.meta.author) && <p className="mt-0.5 truncate text-xs text-muted">{[d.meta.title, d.meta.author].filter(Boolean).join(" - ")}</p>}
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-5">
            {([["Pages", d.page_count], ["Passages", d.passage_count], ["Words", d.word_count.toLocaleString()], ["Size", formatBytes(d.size_bytes)], ["Added", formatDate(d.uploaded_at)]] as [string, string | number][]).map(([k, v]) => (
              <div key={k}><dt className="text-muted">{k}</dt><dd className="font-semibold tabular-nums">{v}</dd></div>))}
          </dl>
          {d.meta.page_note && <p className="mt-2 text-xs text-muted">{d.meta.page_note}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Preview passages" className="focus-ring rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink"><ChevronDown className={cx("h-4 w-4 transition-transform", open && "rotate-180")} /></button>
          <button onClick={onDelete} aria-label={`Delete ${d.name}`} className="focus-ring rounded-lg p-2 text-muted hover:bg-bad-bg/50 hover:text-bad"><Trash2 className="h-4 w-4" /></button>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
            <div className="space-y-2 border-t border-line bg-sunken/40 px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted">Indexed passages (first {detail.data?.passages.length ?? "..."})</p>
              {detail.loading ? <Spinner /> : detail.error ? <p className="text-sm text-bad">{detail.error}</p> : detail.data?.passages.map((p) => (
                <p key={p.id} className="rounded-lg bg-surface px-3 py-2 text-sm leading-relaxed"><Badge tone="neutral" className="mr-2">p.{p.page}</Badge>{p.text}</p>))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}

export default function Library() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [ext, setExt] = useState("");
  const dq = useDebounced(q);
  const docs = useAsync(() => api.documents(dq, ext), [dq, ext]);
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [samplesBusy, setSamplesBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const info = docs.data?.index;
  usePoll(() => docs.reload(), 1500, info?.state === "building");

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    try {
      const r = await api.upload(files);
      r.results.forEach((x) => { if (!x.ok) toast.error(`Could not add ${x.filename}`, x.error); else if (x.duplicate) toast.info(`${x.filename} is already in the library`); });
      if (r.uploaded) toast.success(`Added ${r.uploaded} document${r.uploaded > 1 ? "s" : ""}`, "Rebuilding indexes...");
      docs.reload();
    } catch (e) { toast.error("Upload failed", (e as Error).message); } finally { setUploading(false); }
  };
  const confirmDelete = async () => {
    if (!toDelete) return;
    setBusy(true);
    try { await api.deleteDocument(toDelete.id); toast.success(`Deleted ${toDelete.name}`, "Indexes are rebuilding."); setToDelete(null); docs.reload(); }
    catch (e) { toast.error("Delete failed", (e as Error).message); } finally { setBusy(false); }
  };
  const rebuild = async () => {
    setRebuilding(true);
    try { await api.rebuildIndex(); toast.info("Rebuilding indexes..."); setTimeout(docs.reload, 800); }
    catch (e) { toast.error("Rebuild failed", (e as Error).message); } finally { setRebuilding(false); }
  };
  const loadSamples = async () => {
    setSamplesBusy(true);
    try { const r = await api.loadSamples(); toast.success(r.loaded.length ? "Sample documents added" : "Samples already loaded"); docs.reload(); }
    catch (e) { toast.error("Could not load samples", (e as Error).message); } finally { setSamplesBusy(false); }
  };

  const list = docs.data?.documents ?? [];
  const filtering = !!dq || !!ext;

  return (
    <>
      <PageHeader eyebrow="Trusted sources" title="Evidence library" subtitle="Everything TruthLens may cite. Add or remove documents and the BM25 and dense indexes update automatically."
        actions={<><Button variant="secondary" icon={RefreshCw} loading={rebuilding} onClick={() => void rebuild()}>Rebuild indexes</Button>
          <Button icon={FileUp} loading={uploading} onClick={() => fileRef.current?.click()}>Upload documents</Button></>} />
      <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt" className="hidden" aria-label="Choose files" onChange={(e) => { void upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />

      {info && (
        <Card className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2 px-5 py-4 text-sm">
          <span className="flex items-center gap-2 font-semibold"><Database className="h-4 w-4 text-secondary" />Index
            <Badge tone={info.state === "ready" ? "ok" : info.state === "error" ? "bad" : info.state === "building" ? "warn" : "neutral"}>{info.state}</Badge></span>
          <span className="text-muted"><b className="text-ink tabular-nums">{info.passages}</b> passages in <b className="text-ink tabular-nums">{info.documents}</b> documents</span>
          {info.embedding_backend && <span className="text-muted">Dense: <b className="text-ink">{info.embedding_backend}</b></span>}
          {info.state === "error" && <span className="text-bad">{info.message}</span>}
          {info.state === "empty" && info.passages === 0 && !list.length ? null : info.state === "ready" && info.build_seconds != null && <span className="text-muted">Built in {info.build_seconds}s</span>}
        </Card>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, title or author" aria-label="Search documents" className="input pl-10" />
        </div>
        <div className="flex gap-1.5" role="group" aria-label="Filter by type">
          {EXTS.map((e) => (
            <button key={e.v} onClick={() => setExt(e.v)} aria-pressed={ext === e.v}
              className={cx("focus-ring rounded-full border px-3.5 py-1.5 text-sm font-semibold transition", ext === e.v ? "border-brand bg-brand text-brand-fg" : "border-line bg-surface text-muted hover:text-ink")}>{e.l}</button>))}
        </div>
      </div>

      <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); void upload(Array.from(e.dataTransfer.files)); }}
        className={cx("rounded-2xl transition", dragging && "ring-2 ring-accent ring-offset-4 ring-offset-bg")}>
        {docs.loading && !docs.data ? <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
          : docs.error && !docs.data ? <ErrorState message={docs.error} onRetry={docs.reload} />
          : list.length === 0 ? (
            filtering ? <EmptyState icon={Search} title="No documents match" body="Try a different search or clear the filters." action={<Button variant="secondary" onClick={() => { setQ(""); setExt(""); }}>Clear filters</Button>} />
              : <EmptyState icon={LibIcon} title="Your library is empty" body="Drop PDF, DOCX or TXT files anywhere on this page, or load the built-in samples to explore the app."
                  action={<div className="flex flex-wrap justify-center gap-2"><Button icon={FileUp} onClick={() => fileRef.current?.click()}>Upload documents</Button><Button variant="secondary" icon={Sparkles} loading={samplesBusy} onClick={() => void loadSamples()}>Load samples</Button></div>} />
          ) : (
            <div className="space-y-3">{list.map((d) => <DocCard key={d.id} d={d} onDelete={() => setToDelete(d)} />)}</div>
          )}
      </div>

      <ConfirmDialog open={!!toDelete} busy={busy} onClose={() => setToDelete(null)} onConfirm={() => void confirmDelete()} title="Delete this document?"
        body={<>&ldquo;{toDelete?.name}&rdquo; and its indexed passages will be removed. Past reports keep their saved evidence text.</>} />
    </>
  );
}
