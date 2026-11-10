"""The three baseline classifiers (the fourth system is the app's own aggregation + abstention)."""
from __future__ import annotations

import re

from ..config import STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED
from ..services.nli import NLIScores
from ..services.text_utils import content_words

_NEG = re.compile(r"\b(?:not|no|never|none|neither|nor|cannot|without|nobody|nothing|nowhere)\b|n't", re.IGNORECASE)


def has_negation(text: str) -> bool:
    return bool(_NEG.search(text))


# ---- Baseline 1: BM25 + keyword rules ---------------------------------------------------------
def keyword_features(claim: str, passage_texts: list[str]) -> tuple[float, bool, int]:
    """(best overlap of claim content words with any passage, negation mismatch on that passage, its rank index)."""
    cw = content_words(claim)
    if not cw or not passage_texts:
        return 0.0, False, 0
    best, best_i = -1.0, 0
    for i, t in enumerate(passage_texts):
        ov = len(cw & content_words(t)) / len(cw)
        if ov > best:
            best, best_i = ov, i
    mismatch = has_negation(claim) != has_negation(passage_texts[best_i])
    return best, mismatch, best_i


def keyword_classify(features: tuple[float, bool, int], overlap_support: float, overlap_contra: float) -> tuple[str, int]:
    overlap, mismatch, idx = features
    if overlap >= overlap_contra and mismatch:
        return STATUS_CONTRADICTED, idx
    if overlap >= overlap_support:
        return STATUS_SUPPORTED, idx
    return STATUS_INSUFFICIENT, idx


# ---- Baseline 2: dense similarity ----------------------------------------------------------------
def dense_classify(max_similarity: float | None, threshold: float) -> str:
    """Similarity can only say 'related'; it has no notion of contradiction, so it never predicts CONTRADICTED."""
    return STATUS_SUPPORTED if (max_similarity is not None and max_similarity >= threshold) else STATUS_INSUFFICIENT


# ---- Baseline 3: retrieval + NLI argmax (no thresholds, no aggregation, no abstention) ------------
def nli_argmax_classify(scores: list[NLIScores]) -> tuple[str, int | None]:
    if not scores:
        return STATUS_INSUFFICIENT, None
    best = max(range(len(scores)), key=lambda i: max(scores[i].entailment, scores[i].contradiction))
    lab = scores[best].argmax
    return {"entailment": STATUS_SUPPORTED, "contradiction": STATUS_CONTRADICTED}.get(lab, STATUS_INSUFFICIENT), best
