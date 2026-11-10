# FEVER evaluation

This folder holds everything needed to evaluate TruthLens on **FEVER** (Fact Extraction and VERification).
All numbers are computed from real runs - nothing is hard-coded - and are written to `results/latest.json`
(also shown on the app's **Evaluation** page).

## Systems compared

| Key | System |
|---|---|
| `bm25_keyword` | BM25 retrieval + keyword rules (claim-word overlap, negation mismatch) |
| `dense_similarity` | Dense retrieval + similarity threshold (can never predict *contradicted*) |
| `retrieval_nli` | BM25 top-k + NLI, label = argmax of the best-scoring pair (no thresholds / aggregation / abstention) |
| `proposed` | Hybrid BM25 + dense (RRF) + NLI on every passage + evidence aggregation + abstention |

Label mapping: `SUPPORTS -> SUPPORTED`, `REFUTES -> CONTRADICTED`, `NOT ENOUGH INFO -> INSUFFICIENT_EVIDENCE`.

## Metrics

Accuracy, macro-F1, macro precision / recall, per-class precision / recall / F1, confusion matrix,
**Evidence Recall@K** (gold evidence group fully inside top-K), Evidence Hit@K, **Evidence Precision@K**,
**citation correctness** (cited passage contains a gold sentence), FEVER-style score (label correct and evidence cited),
**abstention coverage / selective error rate / abstain precision / abstain recall**, and processing time per claim.

## Setup (once)

```bash
python evaluation/download_fever.py --split paper_dev      # claims (~ a few MB) + wiki-pages.zip (~1.7 GB)
# claims only (to try the pipeline structure): python evaluation/download_fever.py --claims-only
```

If the download fails, fetch the files manually from <https://fever.ai/dataset/fever.html> and place them as:

```
evaluation/data/fever/paper_dev.jsonl            (or shared_task_dev.jsonl)
evaluation/data/fever/wiki-pages/wiki-001.jsonl ... wiki-109.jsonl
```

## Run

```bash
python evaluation/run_fever_eval.py --sample-size 150               # default, balanced 50/50/50
python evaluation/run_fever_eval.py --sample-size 60 --top-k 3 --distractors 150   # small, for weak laptops
```

Or press **Run evaluation** on the Evaluation page. The run executes in the background.

## Methodology (read before quoting numbers)

* **Closed subset corpus.** Searching all 5.4 M Wikipedia pages is too heavy for a laptop. The corpus is the gold evidence pages
  of the sampled claims plus `--distractors` random pages, cut into sentence-window passages. Retrieval is therefore easier than on
  the official task and **results are not comparable with the FEVER leaderboard**.
* **Fair tuning.** A stratified calibration split (default 20 %) is used only to tune each system's thresholds by macro-F1;
  every reported metric comes from the remaining test split. Set `--calibration-fraction 0` to use default thresholds.
* **No leakage.** The default NLI model (`cross-encoder/nli-deberta-v3-base`) was trained on SNLI + MultiNLI, not FEVER.
  `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` *was* trained on FEVER-NLI; if selected, the report carries a leakage warning.
* **Sample size.** With ~100 test claims, one claim moves accuracy by about 1 point. Use more claims before drawing conclusions.
* The sampling seed (`--seed`) and corpus are cached in `cache/` so repeated runs are comparable.
