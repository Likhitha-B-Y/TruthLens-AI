# Architecture and design notes

## Principles

1. **Evidence traceability.** Every verdict stores the passages it used with document name, page, text, BM25 / dense / fused scores and NLI probabilities.
   Past reports stay readable even if a document is later deleted, because evidence text is saved inside the session.
2. **Retrieval is not verification.** Similarity decides *which passages to read*. Only NLI decides support or contradiction.
3. **Abstain honestly.** Weak, missing or conflicting evidence never becomes a confident label.
4. **No fake AI.** If the NLI model cannot load, verification fails with an explanatory message. The only fallback is for *dense retrieval*
   (TF-IDF + LSA), and it is labelled wherever it is used.
5. **Local and light.** CPU inference, models loaded once, embeddings cached in SQLite, background jobs for long work.

## Backend modules

| Module | Responsibility |
|---|---|
| `config.py` | `Paths`, `RuntimeSettings` (pydantic-validated), model choices |
| `database.py` | SQLite: `documents`, `pages`, `passages`, `embeddings` (cache), `sessions`, `settings`, `eval_runs` |
| `services/document_processing.py` | PDF / DOCX / TXT extraction, cleaning, sentence-aligned overlapping chunking, safe filenames |
| `services/claim_extraction.py` | Sentence split, meta / question filtering, compound splitting, relative clauses, pronoun resolution |
| `services/embeddings.py` | `SentenceTransformerEmbedder`, `TfidfLsaEmbedder` (fallback) |
| `services/retrieval.py` | `HybridRetriever`: BM25Okapi + FAISS `IndexFlatIP`, weighted RRF, de-duplication, document filter |
| `services/nli.py` | `DebertaNLI` (batching, length-sorted, label map from `config.id2label`) |
| `services/aggregation.py` | Per-passage relation, conflict handling, abstention, review flags, explanations, session summary |
| `services/managers.py` | `SettingsStore`, `ModelManager` (background load, status), `IndexManager` (lazy rebuild, re-chunk on setting change, embedding cache) |
| `services/pipeline.py` | `run_verification`: claims -> retrieval -> NLI -> aggregation -> persist, with progress; `Services` container |
| `services/report.py` | ReportLab PDF with Unicode font fallback |
| `evaluation/` | FEVER loading, baselines, metrics, runner with calibration split |
| `api/` | Thin routers; validation via pydantic; global exception handlers (DocumentError 422, VerificationError 400, ModelLoadError 503) |

## Data flow details

* **Upload:** file -> temp -> hash (duplicates detected) -> extract pages -> store pages -> chunk -> store passages -> mark index dirty -> background rebuild.
* **Index:** one corpus-wide BM25 + FAISS index; verification can restrict to selected documents by masking at query time. Embeddings are keyed by
  `(sha256(passage text), model name)` so unchanged passages are never re-embedded after edits or restarts. Changing chunk settings re-chunks every
  document (raw page text is stored) and prunes stale embeddings.
* **Verification:** runs on a single background worker thread (so concurrent requests queue instead of fighting for CPU); the client polls the session
  for stage + progress. `wait=true` makes the call synchronous (used by tests and scripts).
* **Fusion:** `score = sum(weight_r / (k + rank_r))` over BM25 and dense lists (default `k = 60`). Near-duplicate passages (token Jaccard >= 0.9, produced by overlapping
  chunks) are dropped so top-K contains distinct evidence.

## Aggregation rules (all thresholds configurable)

```
supports(p)    = P_ent >= entail_threshold  and  P_ent - max(P_con, P_neu) >= margin
contradicts(p) = P_con >= contradict_threshold and P_con - max(P_ent, P_neu) >= margin

SUPPORTED     : some supports, none contradicts
CONTRADICTED  : some contradicts, none supports
CONFLICT      : both -> INSUFFICIENT_EVIDENCE + needs_review, both passages displayed
INSUFFICIENT  : neither (neutral / weak / no evidence)

needs_review  : conflict | decisive confidence < review_threshold | abstention with max(P_ent, P_con) >= near_miss_floor | no evidence
```

Claim-level scores shown in the UI are those of the *decisive* passage (best supporting, best contradicting, or most neutral), so they always sum to 1.

## Evaluation design

See `evaluation/README.md`. Key choices: balanced sampling per label, closed subset corpus with distractors, calibration / test split for threshold tuning,
NLI scores computed once and reused across methods with per-pair timing, metrics computed by scikit-learn plus small tested functions for retrieval, citation and
abstention metrics.

## Frontend

React Router pages under an `AppShell`; data via a tiny `useAsync` / `usePoll` layer and a typed API client; theme via CSS variables (light / dark) mapped into Tailwind
colour tokens; Recharts for charts; Framer Motion for transitions. The backend serves `frontend/dist` (SPA fallback) so a single process serves UI and API in production mode.

## Security notes

Uploads are size-limited (25 MB), type-checked by extension, stored under hashed names, and filenames are sanitised. SQL uses parameter binding. PDF report text is XML-escaped.
CORS allows only localhost origins. There is no authentication: bind to localhost only (the default).
