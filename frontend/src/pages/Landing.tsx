import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, BookMarked, FileSearch, FileText, GitMerge, Layers, Moon, ScanText, Scale, ShieldCheck, Sun, Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Logo, cx } from "../components/ui";
import { STATUS_META } from "../lib/format";
import { useTheme } from "../lib/theme";
import type { Status } from "../lib/types";

/* The hero is a looping illustration: an AI answer whose claims are checked one by one.
   It is a static demo (not live results) and is labelled as such. */
const DEMO: { text: string; status: Status; note: string }[] = [
  { text: "The Eiffel Tower was completed in 1889.", status: "SUPPORTED", note: "factsheet.txt, p.1" },
  { text: "It is 150 metres tall.", status: "CONTRADICTED", note: "says 330 m" },
  { text: "Its restaurant holds three Michelin stars.", status: "INSUFFICIENT_EVIDENCE", note: "not in documents" },
];

function LensDemo() {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? DEMO.length : 0);
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setStep((s) => (s >= DEMO.length + 2 ? 0 : s + 1)), 1500);
    return () => clearInterval(id);
  }, [reduce]);

  return (
    <div className="relative">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-secondary/15 via-accent/10 to-transparent blur-2xl" />
      <div className="card p-6 shadow-pop sm:p-7">
        <div className="mb-4 flex items-center justify-between">
          <span className="eyebrow">AI answer</span>
          <span className="rounded-full bg-sunken px-2.5 py-1 text-[11px] font-semibold text-muted">Illustration</span>
        </div>
        <div className="space-y-4">
          {DEMO.map((d, i) => {
            const checked = step > i;
            const m = STATUS_META[d.status];
            return (
              <div key={d.text}>
                <p className="relative text-[17px] leading-relaxed">
                  <span className={cx("rounded px-1 py-0.5 transition-colors duration-500", checked ? `${m.bg}` : "bg-transparent")}>{d.text}</span>
                </p>
                <div className="mt-1.5 h-6">
                  {checked && (
                    <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className={cx("inline-flex items-center gap-1.5 text-xs font-semibold", m.text)}>
                      <m.Icon className="h-4 w-4" />{m.label}<span className="font-medium text-muted">&middot; {d.note}</span>
                    </motion.div>
                  )}
                  {!checked && step === i && <span className="text-xs font-medium text-muted">Checking evidence...</span>}
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-5 flex h-2.5 overflow-hidden rounded-full bg-sunken">
          {DEMO.map((d, i) => <div key={i} className={cx("flex-1 transition-all duration-700", step > i ? STATUS_META[d.status].bar : "bg-transparent")} />)}
        </div>
      </div>
    </div>
  );
}

const FEATURES = [
  { icon: Layers, title: "Hybrid evidence retrieval", body: "BM25 keyword search and dense semantic vectors are fused, de-duplicated and ranked. Retrieval only finds candidates; it never decides the verdict." },
  { icon: Scale, title: "Real inference, not similarity", body: "A DeBERTa NLI model scores entailment, contradiction and neutrality for every claim and evidence pair." },
  { icon: ShieldCheck, title: "Abstains when unsure", body: "Weak or missing evidence becomes Insufficient Evidence. Conflicting sources are shown side by side, never forced into a verdict." },
  { icon: BookMarked, title: "Traceable to the page", body: "Every verdict links to the document, page and exact passage, with retrieval and NLI scores you can inspect." },
  { icon: FileText, title: "PDF reports", body: "Export a branded report with claims, labels, scores, evidence and review warnings to share or archive." },
  { icon: Gauge, title: "Measured on FEVER", body: "Compare four systems with real metrics: macro-F1, evidence recall, citation correctness and abstention behaviour." },
];

const STEPS = [
  { icon: ScanText, title: "Paste an AI answer", body: "Drop in text from any assistant." },
  { icon: GitMerge, title: "Extract claims", body: "Sentences become atomic, editable claims." },
  { icon: FileSearch, title: "Retrieve evidence", body: "BM25 + dense search over your documents." },
  { icon: Scale, title: "Run NLI", body: "Entailment, contradiction or neutral." },
  { icon: ShieldCheck, title: "Aggregate and abstain", body: "One verdict, or an honest 'not enough evidence'." },
];

export default function Landing() {
  const { resolved, toggle } = useTheme();
  return (
    <div className="min-h-screen overflow-x-clip">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-8">
          <Link to="/" className="focus-ring rounded-lg" aria-label="TruthLens AI"><Logo /></Link>
          <nav className="hidden items-center gap-7 text-sm font-semibold text-muted md:flex" aria-label="Sections">
            <a href="#features" className="hover:text-ink">Features</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <Link to="/app/evaluation" className="hover:text-ink">Evaluation</Link>
          </nav>
          <div className="flex items-center gap-2">
            <button onClick={toggle} aria-label="Toggle theme" className="focus-ring grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface text-muted hover:text-ink">
              {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <Link to="/app"><Button size="sm">Open app</Button></Link>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-14 sm:px-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:pt-24">
        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <p className="eyebrow mb-5">Evidence-grounded verification</p>
          <h1 className="font-display text-5xl font-semibold leading-[1.04] sm:text-6xl lg:text-[4.25rem]">
            Don&rsquo;t Just Trust AI. <span className="text-secondary">Verify&nbsp;It.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
            TruthLens AI breaks an AI-generated answer into individual claims and checks each one against the documents you trust,
            showing exactly which passage supports it, contradicts it, or fails to settle it.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/app/verify"><Button size="lg" icon={ArrowRight} className="flex-row-reverse">Get started</Button></Link>
            <a href="#how"><Button size="lg" variant="secondary">See how it works</Button></a>
          </div>
          <p className="mt-6 text-sm text-muted">Runs locally. Free open-source models. No API keys.</p>
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.15 }}>
          <LensDemo />
        </motion.div>
      </section>

      <section id="features" className="border-y border-line bg-surface/60 py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-8">
          <p className="eyebrow mb-3">Why TruthLens</p>
          <h2 className="max-w-2xl font-display text-3xl font-semibold sm:text-4xl">Built to show its work, and to say &ldquo;I don&rsquo;t know&rdquo;.</h2>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }} transition={{ delay: (i % 3) * 0.07 }}
                className="card p-6">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-secondary/10 text-secondary"><f.icon className="h-5 w-5" /></span>
                <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="mx-auto max-w-6xl px-4 py-20 sm:px-8">
        <p className="eyebrow mb-3">How it works</p>
        <h2 className="max-w-2xl font-display text-3xl font-semibold sm:text-4xl">From a paragraph to a verdict in five steps.</h2>
        <ol className="relative mt-12 grid gap-6 md:grid-cols-5">
          <div className="absolute left-0 right-0 top-6 -z-10 hidden h-px bg-line md:block" aria-hidden="true" />
          {STEPS.map((s, i) => (
            <motion.li key={s.title} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }} className="relative">
              <span className="grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface text-brand shadow-card dark:text-ink"><s.icon className="h-5 w-5" /></span>
              <p className="mt-4 text-xs font-bold text-secondary">STEP {i + 1}</p>
              <h3 className="mt-1 font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{s.body}</p>
            </motion.li>
          ))}
        </ol>

        <div className="card mt-16 flex flex-col items-start justify-between gap-6 bg-brand p-8 text-brand-fg sm:flex-row sm:items-center sm:p-10">
          <div>
            <h3 className="font-display text-2xl font-semibold">Try it with the built-in sample documents.</h3>
            <p className="mt-1.5 max-w-lg text-sm text-white/75">Load sample references and answers that demonstrate supported, contradicted and insufficient-evidence claims.</p>
          </div>
          <Link to="/app/verify"><Button size="lg" variant="secondary" className="!border-white/0">Start verifying</Button></Link>
        </div>
      </section>

      <footer className="border-t border-line py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-muted sm:flex-row sm:px-8">
          <Logo className="scale-90" />
          <p>TruthLens AI &ndash; Evidence-Grounded Verification of AI-Generated Answers.</p>
          <p>Verdicts are aids, not guarantees. Review important claims yourself.</p>
        </div>
      </footer>
    </div>
  );
}
