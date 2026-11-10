"""FEVER evaluation runner: four systems, real metrics, calibration split for fair threshold tuning."""
from __future__ import annotations

import json
import logging
import platform
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from ..config import (STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED, RuntimeSettings)
from ..database import utcnow
from ..services.aggregation import AggregationConfig, EvidenceItem, aggregate
from ..services.embeddings import TfidfLsaEmbedder
from ..services.retrieval import HybridRetriever, RetrievedPassage
from .baselines import dense_classify, keyword_classify, keyword_features, nli_argmax_classify
from .fever import FeverClaim, build_passages, load_claims, load_or_build_pages
from .metrics import (LABELS, abstention_metrics, citation_metrics, classification_metrics, macro_f1,
                      retrieval_metrics)

log = logging.getLogger(__name__)
Progress = Callable[[str, int, int], None]

METHODS = {
    "bm25_keyword": "BM25 + keyword-based classification",
    "dense_similarity": "Dense similarity-based classification",
    "retrieval_nli": "Retrieval + NLI (BM25 top-k, best-pair argmax)",
    "proposed": "Hybrid retrieval + NLI + aggregation + abstention (proposed)",
}


@dataclass
class EvalConfig:
    fever_path: str = ""
    wiki_dir: str = ""
    sample_size: int = 150
    top_k: int = 5
    window: int = 3
    distractors: int = 300
    calibration_fraction: float = 0.2
    seed: int = 13
    max_k: int = 10


def _rp(retriever: HybridRetriever, hits: list[tuple[int, float]], kind: str, k: int) -> list[RetrievedPassage]:
    out = []
    for rank, (i, s) in enumerate(hits[:k], start=1):
        rp = RetrievedPassage(retriever.passages[i], fused_rank=rank)
        if kind == "bm25":
            rp.bm25_score, rp.bm25_rank = s, rank
        else:
            rp.dense_score, rp.dense_rank = s, rank
        out.append(rp)
    return out


def _split(claims: list[FeverClaim], frac: float, seed: int) -> tuple[list[int], list[int]]:
    rng = random.Random(seed + 1)
    calib, test = [], []
    for label in LABELS:
        idx = [i for i, c in enumerate(claims) if c.label == label]
        rng.shuffle(idx)
        n_cal = int(round(len(idx) * frac))
        calib += idx[:n_cal]
        test += idx[n_cal:]
    return sorted(calib), sorted(test)


def _best(grid: list, score_fn: Callable) -> tuple:
    best, best_s = grid[0], -1.0
    for p in grid:
        s = score_fn(p)
        if s > best_s + 1e-12:
            best, best_s = p, s
    return best, best_s


def run_evaluation_core(cfg: EvalConfig, nli, embedder, settings: RuntimeSettings, claims: list[FeverClaim],
                        pages: dict, progress: Progress | None = None) -> dict:
    prog = progress or (lambda *_: None)
    t_all = time.perf_counter()
    emb = TfidfLsaEmbedder() if embedder.needs_fit else embedder     # never mutate the app's shared embedder
    passages = build_passages(pages, cfg.window)
    if not passages:
        raise ValueError("The subset corpus is empty - check the FEVER wiki-pages directory.")
    texts = [p.text for p in passages]

    # ---- index ------------------------------------------------------------------------------
    t = time.perf_counter()
    if emb.needs_fit:
        emb.fit(texts)
    vecs = []
    for s in range(0, len(texts), 128):
        vecs.append(emb.encode(texts[s:s + 128]))
        prog("embedding_corpus", min(s + 128, len(texts)), len(texts))
    matrix = np.vstack(vecs)
    retriever = HybridRetriever(passages, matrix, emb)
    index_seconds = time.perf_counter() - t

    # ---- retrieval for every claim -----------------------------------------------------------
    max_k = max(cfg.max_k, cfg.top_k)
    cand = max(settings.bm25_candidates, max_k)
    ret = []
    for ci, c in enumerate(claims):
        prog("retrieving", ci, len(claims))
        t0 = time.perf_counter(); bm = retriever.search_bm25(c.claim, cand); t_bm = time.perf_counter() - t0
        t0 = time.perf_counter(); de = retriever.search_dense(c.claim, max(settings.dense_candidates, max_k)); t_de = time.perf_counter() - t0
        t0 = time.perf_counter()
        hy = retriever.fuse(bm, de, max_k, rrf_k=settings.rrf_k, bm25_weight=settings.bm25_weight,
                            dense_weight=settings.dense_weight)
        t_fu = time.perf_counter() - t0
        ret.append({"bm25": _rp(retriever, bm, "bm25", max_k), "dense": _rp(retriever, de, "dense", max_k),
                    "hybrid": hy, "t_bm": t_bm, "t_de": t_de, "t_fu": t_fu})

    # ---- NLI on the union of pairs (computed once, timed per pair) ------------------------------
    nli_k = min(cfg.top_k, max_k)
    pair_keys: dict[tuple[int, int], None] = {}
    for ci, r in enumerate(ret):
        for rp in r["bm25"][:nli_k] + r["hybrid"][:nli_k]:
            pair_keys[(ci, rp.passage.id)] = None
    keys = list(pair_keys)
    nli_scores: dict[tuple[int, int], object] = {}
    nli_time: dict[tuple[int, int], float] = {}
    for s in range(0, len(keys), 16):
        chunk = keys[s:s + 16]
        t0 = time.perf_counter()
        out = nli.predict([passages[pid].text for _, pid in chunk], [claims[ci].claim for ci, _ in chunk])
        dt = (time.perf_counter() - t0) / len(chunk)
        for k, sc in zip(chunk, out):
            nli_scores[k], nli_time[k] = sc, dt
        prog("nli_inference", min(s + 16, len(keys)), len(keys))

    calib, test = _split(claims, cfg.calibration_fraction, cfg.seed)
    tune = len(calib) >= 30
    prog("evaluating", 0, 1)

    # ---- per-method predictors (pure functions of cached features) -------------------------------
    kw_feats = [keyword_features(c.claim, [rp.passage.text for rp in ret[i]["bm25"][:cfg.top_k]])
                for i, c in enumerate(claims)]
    dense_max = [(ret[i]["dense"][0].dense_score if ret[i]["dense"] else None) for i in range(len(claims))]
    base_agg = AggregationConfig.from_settings(settings)

    def ev_items(ci: int, rps: list[RetrievedPassage]) -> list[EvidenceItem]:
        return [EvidenceItem(passage=rp.to_dict(), nli=nli_scores[(ci, rp.passage.id)]) for rp in rps[:nli_k]]

    def pred_kw(ci, p):
        lab, idx = keyword_classify(kw_feats[ci], *p)
        rps = ret[ci]["bm25"][:cfg.top_k]
        return lab, (rps[idx].passage.meta if rps else None)

    def pred_dense(ci, p):
        lab = dense_classify(dense_max[ci], p)
        return lab, (ret[ci]["dense"][0].passage.meta if ret[ci]["dense"] else None)

    def pred_nli(ci, _p):
        rps = ret[ci]["bm25"][:nli_k]
        lab, idx = nli_argmax_classify([nli_scores[(ci, rp.passage.id)] for rp in rps])
        return lab, (rps[idx].passage.meta if idx is not None else None)

    def pred_prop(ci, p):
        e, c = p
        agg = AggregationConfig(e, c, base_agg.margin, base_agg.review_threshold, base_agg.near_miss_floor)
        items = ev_items(ci, ret[ci]["hybrid"])
        v = aggregate(items, agg)
        cited = None
        if v.decisive_index is not None:
            pid = items[v.decisive_index].passage["passage_id"]
            cited = passages[pid].meta
        return v.status, cited

    steps = [round(x, 2) for x in np.arange(0.50, 0.96, 0.05)]
    grids = {
        "bm25_keyword": ([(a, b) for a in steps for b in [0.4, 0.5, 0.6, 0.7, 0.8]], pred_kw, (0.8, 0.6)),
        "dense_similarity": ([round(x, 3) for x in np.linspace(0.2, 0.9, 36)], pred_dense, 0.5),
        "retrieval_nli": ([None], pred_nli, None),
        "proposed": ([(e, c) for e in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95] for c in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]],
                     pred_prop, (base_agg.entail_threshold, base_agg.contradict_threshold)),
    }
    methods_out: dict = {}
    pred_cache: dict[str, dict[int, tuple]] = {}
    for key, (grid, fn, default) in grids.items():
        params = default
        calib_f1 = None
        if tune and len(grid) > 1:
            params, calib_f1 = _best(grid, lambda p: macro_f1([claims[i].label for i in calib],
                                                              [fn(i, p)[0] for i in calib]))
        preds = {i: fn(i, params) for i in test}
        pred_cache[key] = preds
        gold = [claims[i].label for i in test]
        pl = [preds[i][0] for i in test]
        cit = citation_metrics([{"gold": claims[i].label, "pred": preds[i][0], "gold_groups": claims[i].gold_groups,
                                 "cited_meta": preds[i][1]} for i in test])
        # timing
        per = []
        for i in test:
            r = ret[i]
            if key == "bm25_keyword":
                per.append((r["t_bm"], 0.0))
            elif key == "dense_similarity":
                per.append((r["t_de"], 0.0))
            elif key == "retrieval_nli":
                per.append((r["t_bm"], sum(nli_time[(i, rp.passage.id)] for rp in r["bm25"][:nli_k])))
            else:
                t0 = time.perf_counter(); pred_prop(i, params); t_ag = time.perf_counter() - t0
                per.append((r["t_bm"] + r["t_de"] + r["t_fu"] + t_ag,
                            sum(nli_time[(i, rp.passage.id)] for rp in r["hybrid"][:nli_k])))
        ret_s = float(np.mean([a for a, _ in per])); nli_s = float(np.mean([b for _, b in per]))
        methods_out[key] = {
            "name": METHODS[key], "thresholds": _fmt_params(key, params),
            "tuned_on_calibration": bool(tune and len(grid) > 1), "calibration_macro_f1": calib_f1,
            "metrics": classification_metrics(gold, pl),
            "abstention": abstention_metrics(gold, pl),
            "citation": cit,
            "timing": {"retrieval_s_per_claim": ret_s, "nli_s_per_claim": nli_s,
                       "total_s_per_claim": ret_s + nli_s, "total_s": (ret_s + nli_s) * len(test)},
        }

    ks = [k for k in (1, 3, 5, 10) if k <= max_k]
    if cfg.top_k not in ks:
        ks = sorted(set(ks + [cfg.top_k]))
    retrieval = {}
    for name in ("bm25", "dense", "hybrid"):
        retrieval[name] = retrieval_metrics(
            [{"verifiable": claims[i].verifiable, "gold_groups": claims[i].gold_groups,
              "retrieved_meta": [rp.passage.meta for rp in ret[i][name]]} for i in test], ks)

    examples = []
    for i in test[:40]:
        examples.append({"claim": claims[i].claim, "gold": claims[i].label,
                         **{k: pred_cache[k][i][0] for k in methods_out}})

    counts = lambda idx: {lab: sum(1 for i in idx if claims[i].label == lab) for lab in LABELS}  # noqa: E731
    notes = [
        "Closed subset corpus: gold evidence pages of the sampled claims plus random distractor pages. "
        "Absolute numbers are NOT comparable with FEVER leaderboard results (full Wikipedia).",
        "Thresholds of every method were tuned on a held-out calibration split; all reported metrics use the remaining test split."
        if tune else "Calibration split too small (<30 claims): default thresholds were used, nothing was tuned.",
        "Retrieval + NLI uses an argmax over the best-scoring pair, with no thresholds, aggregation or abstention.",
    ]
    nli_name = getattr(nli, "model_name", "unknown")
    if "fever" in nli_name.lower():
        notes.append(f"WARNING: '{nli_name}' was trained on FEVER-NLI data; these results may be inflated by train/test leakage.")
    if embedder.needs_fit:
        notes.append("Dense retrieval used the TF-IDF + LSA fallback, not a transformer embedding model.")
    return {
        "generated_at": utcnow(),
        "config": cfg.__dict__,
        "dataset": {"sampled_claims": len(claims), "all": counts(range(len(claims))),
                    "calibration": {"n": len(calib), "labels": counts(calib)},
                    "test": {"n": len(test), "labels": counts(test)},
                    "corpus": {"pages": len(pages), "passages": len(passages)}},
        "models": {"nli": nli_name, "embedding": emb.name, "device": getattr(nli, "device", "cpu")},
        "environment": {"python": platform.python_version(), "machine": platform.machine(), "system": platform.system()},
        "index_seconds": index_seconds,
        "methods": methods_out, "retrieval": retrieval, "ks": ks, "examples": examples, "notes": notes,
        "total_seconds": time.perf_counter() - t_all,
    }


def _fmt_params(key: str, p) -> dict:
    if key == "bm25_keyword":
        return {"overlap_support": float(p[0]), "overlap_contradict": float(p[1])}
    if key == "dense_similarity":
        return {"similarity_threshold": float(p)}
    if key == "proposed":
        return {"entail_threshold": float(p[0]), "contradict_threshold": float(p[1])}
    return {}


def run_evaluation(svc, run_id: str, cfg: EvalConfig) -> None:
    """Background job used by the API. Persists progress and results."""
    db = svc.db

    def progress(stage: str, done: int, total: int) -> None:
        db.update_eval_run(run_id, progress={"stage": stage, "done": done, "total": total})

    try:
        progress("loading_claims", 0, 1)
        claims = load_claims(cfg.fever_path, cfg.sample_size, cfg.seed)
        progress("reading_wikipedia", 0, 1)
        pages = load_or_build_pages(claims, cfg.wiki_dir, cfg.distractors, cfg.seed, cfg.window,
                                    svc.paths.evaluation / "cache", lambda d, t: progress("reading_wikipedia", d, t))
        results = run_evaluation_core(cfg, svc.models.require_nli(), svc.models.require_embedder(),
                                      svc.settings.get(), claims, pages, progress)
        out_dir = svc.paths.evaluation / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"fever_eval_{run_id}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (out_dir / "latest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        db.update_eval_run(run_id, status="completed", finished_at=utcnow(), results=results,
                           progress={"stage": "done", "done": 1, "total": 1})
    except Exception as e:
        log.exception("Evaluation failed")
        db.update_eval_run(run_id, status="failed", finished_at=utcnow(), error=str(e))
