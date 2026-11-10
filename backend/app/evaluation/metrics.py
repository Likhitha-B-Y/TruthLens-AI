"""Evaluation metrics (all computed from real predictions; nothing is hard-coded)."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from ..config import STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED

LABELS = [STATUS_SUPPORTED, STATUS_CONTRADICTED, STATUS_INSUFFICIENT]


def classification_metrics(gold: list[str], pred: list[str]) -> dict:
    if not gold:
        return {}
    p, r, f, sup = precision_recall_fscore_support(gold, pred, labels=LABELS, zero_division=0)
    cm = confusion_matrix(gold, pred, labels=LABELS)
    return {
        "n": len(gold),
        "accuracy": float(accuracy_score(gold, pred)),
        "macro_f1": float(np.mean(f)),
        "macro_precision": float(np.mean(p)),
        "macro_recall": float(np.mean(r)),
        "per_class": {lab: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(sup[i])}
                      for i, lab in enumerate(LABELS)},
        "confusion_matrix": {"labels": LABELS, "matrix": cm.tolist()},
    }


def macro_f1(gold: list[str], pred: list[str]) -> float:
    _, _, f, _ = precision_recall_fscore_support(gold, pred, labels=LABELS, zero_division=0)
    return float(np.mean(f))


def abstention_metrics(gold: list[str], pred: list[str]) -> dict:
    """Abstention = predicting INSUFFICIENT_EVIDENCE.
    coverage             share of claims the system gave a definite verdict on
    selective_error_rate error rate among answered claims (wrong SUPPORTED/CONTRADICTED verdicts)
    abstain_precision    share of abstentions that were truly NOT ENOUGH INFO
    abstain_recall       share of NOT ENOUGH INFO claims the system abstained on
    """
    n = len(gold)
    answered = [(g, p) for g, p in zip(gold, pred) if p != STATUS_INSUFFICIENT]
    abst = [(g, p) for g, p in zip(gold, pred) if p == STATUS_INSUFFICIENT]
    nei = [(g, p) for g, p in zip(gold, pred) if g == STATUS_INSUFFICIENT]
    wrong = sum(1 for g, p in answered if g != p)
    return {
        "coverage": len(answered) / n if n else 0.0,
        "abstained": len(abst),
        "answered": len(answered),
        "selective_error_rate": wrong / len(answered) if answered else None,
        "abstain_precision": sum(1 for g, _ in abst if g == STATUS_INSUFFICIENT) / len(abst) if abst else None,
        "abstain_recall": sum(1 for _, p in nei if p == STATUS_INSUFFICIENT) / len(nei) if nei else None,
    }


# ------------------------------------------------------------------ retrieval
def passage_covers(meta: dict, page: str, sent: int) -> bool:
    return meta.get("page_id") == page and sent in meta.get("sent_ids", [])


def retrieval_metrics(per_claim: list[dict], ks: list[int]) -> dict:
    """per_claim items: {"verifiable": bool, "gold_groups": [...], "retrieved_meta": [meta,...] (ranked)}
    Evidence Recall@K    verifiable claims with >=1 gold evidence group fully covered by the top-K passages (FEVER-style)
    Evidence Hit@K       verifiable claims with >=1 gold sentence in the top-K passages
    Evidence Precision@K mean fraction of the top-K passages containing a gold sentence (verifiable claims)
    """
    ver = [c for c in per_claim if c["verifiable"]]
    out: dict = {"n_verifiable": len(ver)}
    for k in ks:
        rec = hit = 0
        precs = []
        for c in ver:
            top = c["retrieved_meta"][:k]
            gold_all = {(p, s) for g in c["gold_groups"] for p, s in g}
            covered = lambda ps: any(passage_covers(m, ps[0], ps[1]) for m in top)  # noqa: E731
            if any(all(covered(ps) for ps in g) for g in c["gold_groups"]):
                rec += 1
            if any(covered(ps) for ps in gold_all):
                hit += 1
            relevant = sum(1 for m in top if any(passage_covers(m, p, s) for p, s in gold_all))
            precs.append(relevant / k)
        n = len(ver) or 1
        out[f"recall@{k}"] = rec / n
        out[f"hit@{k}"] = hit / n
        out[f"precision@{k}"] = float(np.mean(precs)) if precs else 0.0
    return out


def citation_metrics(items: list[dict]) -> dict:
    """items: {"gold": str, "pred": str, "gold_groups": [...], "cited_meta": dict | None}
    Citation correctness = of the claims where the system gave a SUPPORTED/CONTRADICTED verdict, the share whose cited
    passage contains a gold evidence sentence (claims with no gold evidence, i.e. NEI, count as incorrect).
    FEVER-style score = label correct AND (NEI, or the cited passage hits gold evidence)."""
    answered = [i for i in items if i["pred"] != STATUS_INSUFFICIENT]
    ok = 0
    for i in answered:
        gold_all = {(p, s) for g in i["gold_groups"] for p, s in g}
        if i["cited_meta"] and any(passage_covers(i["cited_meta"], p, s) for p, s in gold_all):
            ok += 1
    fever_ok = 0
    for i in items:
        if i["gold"] != i["pred"]:
            continue
        if i["gold"] == STATUS_INSUFFICIENT:
            fever_ok += 1
            continue
        gold_all = {(p, s) for g in i["gold_groups"] for p, s in g}
        if i["cited_meta"] and any(passage_covers(i["cited_meta"], p, s) for p, s in gold_all):
            fever_ok += 1
    return {
        "citation_correctness": ok / len(answered) if answered else None,
        "answered_with_citation": len(answered),
        "fever_style_score": fever_ok / len(items) if items else 0.0,
    }
