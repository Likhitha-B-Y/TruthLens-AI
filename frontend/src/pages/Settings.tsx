import { Cpu, Gauge, Layers, Monitor, Moon, Palette, RefreshCw, RotateCcw, Save, Scale, Sun, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Badge, Button, Card, ErrorState, Notice, PageHeader, Segmented, Skeleton, SliderField, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { useModelStatus } from "../lib/modelStatus";
import { useTheme } from "../lib/theme";
import { useToast } from "../lib/toast";
import type { ModelState, Settings } from "../lib/types";

function Section({ icon: Icon, title, hint, children }: { icon: typeof Cpu; title: string; hint?: string; children: ReactNode }) {
  return (
    <Card className="p-6">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary/10 text-secondary"><Icon className="h-5 w-5" /></span>
        <div><h2 className="font-display text-xl font-semibold">{title}</h2>{hint && <p className="text-sm text-muted">{hint}</p>}</div>
      </div>
      <div className="divide-y divide-line/70 [&>*]:py-3 first:[&>*]:pt-0">{children}</div>
    </Card>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold">{label}</span>
      {hint && <span className="mb-1.5 mt-0.5 block text-xs text-muted">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function StateRow({ s, name }: { s: ModelState; name: string }) {
  const tone = s.state === "ready" ? "ok" : s.state === "error" ? "bad" : "warn";
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl bg-sunken/60 px-4 py-3">
      <div className="min-w-0"><p className="text-sm font-semibold">{name}</p><p className="truncate text-xs text-muted">{s.model ?? "-"}{s.device ? ` on ${s.device}` : ""}</p>
        {s.state !== "ready" && s.message && <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">{s.message}</p>}</div>
      <Badge tone={tone}>{s.state}{s.load_seconds != null && s.state === "ready" ? ` - ${s.load_seconds}s` : ""}</Badge>
    </div>
  );
}

export default function SettingsPage() {
  const toast = useToast();
  const { pref, setPref } = useTheme();
  const { status, reload, refresh } = useModelStatus();
  const data = useAsync(() => api.settings(), []);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (data.data) setDraft(data.data.settings); }, [data.data]);
  const saved = data.data?.settings;
  const dirty = useMemo(() => !!draft && !!saved && JSON.stringify(draft) !== JSON.stringify(saved), [draft, saved]);
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft((d) => (d ? { ...d, [k]: v } : d));
  const modelsChanged = !!draft && !!saved && (draft.nli_model !== saved.nli_model || draft.embedding_model !== saved.embedding_model || draft.embedding_backend !== saved.embedding_backend || draft.device !== saved.device);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const r = await api.saveSettings(draft);
      data.setData({ settings: r.settings, choices: data.data?.choices });
      setDraft(r.settings);
      toast.success("Settings saved", r.models_reloading ? "Models are reloading with the new configuration." : r.reindexing ? "Documents are being re-chunked and re-indexed." : undefined);
      void refresh();
    } catch (e) { toast.error("Could not save settings", (e as Error).message); } finally { setSaving(false); }
  };
  const reset = async () => {
    try { const r = await api.resetSettings(); data.setData({ settings: r.settings, choices: data.data?.choices }); setDraft(r.settings); toast.success("Settings reset to defaults"); void refresh(); }
    catch (e) { toast.error("Reset failed", (e as Error).message); }
  };
  const pickTheme = (t: Settings["theme"]) => { setPref(t); api.saveSettings({ theme: t }).then((r) => { data.setData({ settings: r.settings, choices: data.data?.choices }); setDraft((d) => (d ? { ...d, theme: t } : d)); }).catch(() => undefined); };

  if (data.loading && !draft) return (<><PageHeader title="Settings" /><div className="space-y-5"><Skeleton className="h-48" /><Skeleton className="h-64" /></div></>);
  if (data.error && !draft) return (<><PageHeader title="Settings" /><ErrorState message={data.error} onRetry={data.reload} /></>);
  if (!draft) return null;
  const nliChoices = data.data?.choices?.nli ?? [];
  const embChoices = data.data?.choices?.embedding ?? [];
  const nliNote = nliChoices.find((c) => c.id === draft.nli_model)?.note;
  const pc = (v: number) => `${Math.round(v * 100)}%`;

  return (
    <>
      <PageHeader eyebrow="Configuration" title="Settings" subtitle="Tune models, retrieval and decision thresholds. Everything runs locally and is stored in your SQLite database."
        actions={<><Button variant="secondary" icon={RotateCcw} onClick={() => void reset()}>Reset defaults</Button><Button icon={Save} loading={saving} disabled={!dirty} onClick={() => void save()}>{dirty ? "Save changes" : "Saved"}</Button></>} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Section icon={Palette} title="Appearance">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold">Theme</p><p className="text-xs text-muted">Applied instantly and remembered in this browser.</p></div>
              <Segmented label="Theme" value={pref} onChange={pickTheme} options={[{ value: "light", label: "Light", icon: Sun }, { value: "dark", label: "Dark", icon: Moon }, { value: "system", label: "System", icon: Monitor }]} /></div>
          </Section>

          <Section icon={Cpu} title="Models" hint="Open-source models, downloaded once and cached in data/models.">
            <div className="space-y-2">
              {status ? (<><StateRow s={status.nli} name="NLI verifier" /><StateRow s={status.embedding} name="Dense embeddings" /></>) : <Skeleton className="h-24" />}
              <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => void reload()}>Reload models</Button>
            </div>
            <Field label="NLI model" hint="Premise = evidence, hypothesis = claim.">
              <select className="input" value={nliChoices.some((c) => c.id === draft.nli_model) ? draft.nli_model : "__custom"} onChange={(e) => e.target.value !== "__custom" && set("nli_model", e.target.value)}>
                {nliChoices.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}<option value="__custom">Custom Hugging Face model id...</option>
              </select>
              <input className="input mt-2" value={draft.nli_model} onChange={(e) => set("nli_model", e.target.value)} aria-label="NLI model id" spellCheck={false} />
              {nliNote && <p className="mt-1.5 text-xs text-muted">{nliNote}</p>}
            </Field>
            <Field label="Embedding model" hint="Used for dense retrieval (FAISS).">
              <select className="input" value={embChoices.some((c) => c.id === draft.embedding_model) ? draft.embedding_model : "__custom"} onChange={(e) => e.target.value !== "__custom" && set("embedding_model", e.target.value)}>
                {embChoices.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}<option value="__custom">Custom model id...</option>
              </select>
              <input className="input mt-2" value={draft.embedding_model} onChange={(e) => set("embedding_model", e.target.value)} aria-label="Embedding model id" spellCheck={false} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Dense backend" hint="Auto falls back to TF-IDF/LSA if the model cannot load.">
                <select className="input" value={draft.embedding_backend} onChange={(e) => set("embedding_backend", e.target.value as Settings["embedding_backend"])}>
                  <option value="auto">Auto (recommended)</option><option value="sentence-transformers">Sentence-Transformers only</option><option value="tfidf-lsa">TF-IDF + LSA (no download)</option></select></Field>
              <Field label="Device"><select className="input" value={draft.device} onChange={(e) => set("device", e.target.value as Settings["device"])}><option value="auto">Auto</option><option value="cpu">CPU</option><option value="cuda">GPU (CUDA)</option></select></Field>
            </div>
            <SliderField label="NLI batch size" hint="Lower it if you run out of memory." value={draft.nli_batch_size} min={1} max={32} step={1} onChange={(v) => set("nli_batch_size", v)} />
            {modelsChanged && <Notice tone="warn" title="Model change">Saving reloads the models. The first use of a new model downloads it, which can take a few minutes.</Notice>}
          </Section>
        </div>

        <div className="space-y-6">
          <Section icon={Layers} title="Retrieval" hint="How evidence is found. Retrieval never decides a verdict.">
            <SliderField label="Evidence passages per claim (top-K)" value={draft.top_k} min={1} max={15} step={1} onChange={(v) => set("top_k", v)} hint="Passages returned after fusion and de-duplication." />
            <SliderField label="Passages sent to NLI" value={Math.min(draft.nli_top_k, draft.top_k)} min={1} max={draft.top_k} step={1} onChange={(v) => set("nli_top_k", v)} hint="Cannot exceed top-K. More passages is slower but catches more evidence." />
            <div className="grid gap-x-6 sm:grid-cols-2">
              <SliderField label="BM25 candidates" value={draft.bm25_candidates} min={5} max={100} step={5} onChange={(v) => set("bm25_candidates", v)} />
              <SliderField label="Dense candidates" value={draft.dense_candidates} min={5} max={100} step={5} onChange={(v) => set("dense_candidates", v)} />
              <SliderField label="BM25 weight" value={draft.bm25_weight} min={0} max={3} step={0.1} onChange={(v) => set("bm25_weight", v)} format={(v) => v.toFixed(1)} />
              <SliderField label="Dense weight" value={draft.dense_weight} min={0} max={3} step={0.1} onChange={(v) => set("dense_weight", v)} format={(v) => v.toFixed(1)} />
            </div>
            <SliderField label="RRF constant (k)" value={draft.rrf_k} min={1} max={120} step={1} onChange={(v) => set("rrf_k", v)} hint="Reciprocal-rank-fusion smoothing. 60 is the usual default." />
            <div className="grid gap-x-6 sm:grid-cols-2">
              <SliderField label="Passage size (words)" value={draft.chunk_words} min={40} max={250} step={10} onChange={(v) => set("chunk_words", v)} />
              <SliderField label="Overlap (sentences)" value={draft.chunk_overlap_sentences} min={0} max={3} step={1} onChange={(v) => set("chunk_overlap_sentences", v)} />
            </div>
            {(draft.chunk_words !== saved?.chunk_words || draft.chunk_overlap_sentences !== saved?.chunk_overlap_sentences) && <Notice tone="info">Saving re-chunks every document and rebuilds the indexes.</Notice>}
          </Section>

          <Section icon={Scale} title="NLI thresholds" hint="When evidence counts as decisive. Anything weaker becomes Insufficient Evidence.">
            <SliderField label="Entailment threshold" value={draft.entail_threshold} min={0.4} max={0.99} step={0.01} onChange={(v) => set("entail_threshold", v)} format={pc} hint="Minimum P(entailment) to mark a claim Supported." />
            <SliderField label="Contradiction threshold" value={draft.contradict_threshold} min={0.4} max={0.99} step={0.01} onChange={(v) => set("contradict_threshold", v)} format={pc} hint="Minimum P(contradiction) to mark a claim Contradicted." />
            <SliderField label="Required margin" value={draft.margin} min={0} max={0.4} step={0.01} onChange={(v) => set("margin", v)} format={pc} hint="How far the winning class must lead the others." />
            <SliderField label="Human-review threshold" value={draft.review_threshold} min={0.5} max={1} step={0.01} onChange={(v) => set("review_threshold", v)} format={pc} hint="Verdicts below this confidence are flagged for review." />
            <SliderField label="Near-miss floor" value={draft.near_miss_floor} min={0.1} max={0.9} step={0.01} onChange={(v) => set("near_miss_floor", v)} format={pc} hint="Abstentions leaning at least this far toward a verdict are flagged for review." />
          </Section>

          <Section icon={Wand2} title="Claim extraction">
            <Toggle checked={draft.split_compound} onChange={(v) => set("split_compound", v)} label="Split compound sentences" hint={'Turns "X did A and B" into two atomic claims.'} />
            <Toggle checked={draft.resolve_pronouns} onChange={(v) => set("resolve_pronouns", v)} label="Resolve leading pronouns" hint={'Replaces "It..." with the previous sentence\u2019s subject.'} />
            <SliderField label="Maximum claims per answer" value={draft.max_claims} min={5} max={150} step={5} onChange={(v) => set("max_claims", v)} />
          </Section>
        </div>
      </div>

      <p className="mt-6 flex items-center gap-2 text-xs text-muted"><Gauge className="h-4 w-4" />Changes apply to new verifications. Past reports keep the settings they were created with.</p>
    </>
  );
}
