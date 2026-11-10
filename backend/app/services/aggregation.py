"""Evidence aggregation, conflict handling and abstention.

Input: per-evidence NLI scores for one claim. Output: one of three labels
  SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE
plus a confidence, the decisive evidence, review flags and a plain-language explanation.

Rules (all thresholds configurable):
  1. An evidence passage SUPPORTS if P(entailment) >= entail_threshold and it beats the other classes by `margin`.
  2. It CONTRADICTS if P(contradiction) >= contradict_threshold and it beats the others by `margin`.
  3. Supporting AND contradicting passages -> conflicting sources: abstain (INSUFFICIENT_EVIDENCE), flag for review,
     show both sides. We never force a verdict when the trusted sources disagree.
  4. Only supporting -> SUPPORTED; only contradicting -> CONTRADICTED.
  5. Nothing decisive (neutral, weak, no evidence) -> abstain with INSUFFICIENT_EVIDENCE.
  6. Decisions below `review_threshold`, conflicts, and near-misses are flagged for human review.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED
from .nli import NLIScores


@dataclass
class AggregationConfig:
    entail_threshold: float = 0.70
    contradict_threshold: float = 0.70
    margin: float = 0.10
    review_threshold: float = 0.85
    near_miss_floor: float = 0.40

    @classmethod
    def from_settings(cls, s) -> "AggregationConfig":
        return cls(s.entail_threshold, s.contradict_threshold, s.margin, s.review_threshold, s.near_miss_floor)


@dataclass
class EvidenceItem:
    """One retrieved passage plus its NLI scores for a claim."""
    passage: dict                       # RetrievedPassage.to_dict()
    nli: NLIScores
    relation: str = "neutral"           # supports | contradicts | neutral  (after thresholds)

    def to_dict(self) -> dict:
        return {**self.passage, "nli": self.nli.to_dict(), "relation": self.relation}


@dataclass
class Verdict:
    status: str
    confidence: float
    scores: NLIScores | None
    decisive_index: int | None
    conflict: bool
    needs_review: bool
    review_reasons: list[str] = field(default_factory=list)
    explanation: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    supporting: list[int] = field(default_factory=list)
    contradicting: list[int] = field(default_factory=list)


def classify_evidence(scores: NLIScores, cfg: AggregationConfig) -> str:
    e, c, n = scores.entailment, scores.contradiction, scores.neutral
    if e >= cfg.entail_threshold and e - max(c, n) >= cfg.margin:
        return "supports"
    if c >= cfg.contradict_threshold and c - max(e, n) >= cfg.margin:
        return "contradicts"
    return "neutral"


def _src(item: EvidenceItem) -> str:
    p = item.passage
    return f"{p.get('doc_name', 'document')} (page {p.get('page', '?')})"


def aggregate(evidence: list[EvidenceItem], cfg: AggregationConfig) -> Verdict:
    """Combine NLI results over retrieved evidence into one claim-level verdict."""
    if not evidence:
        return Verdict(
            status=STATUS_INSUFFICIENT, confidence=0.0, scores=None, decisive_index=None, conflict=False,
            needs_review=True, review_reasons=["no_evidence_retrieved"],
            explanation="No passage in the trusted documents was retrieved for this claim, so it cannot be verified. "
                        "Upload a relevant reference document or review the claim manually.",
        )

    for item in evidence:
        item.relation = classify_evidence(item.nli, cfg)
    sup = [i for i, it in enumerate(evidence) if it.relation == "supports"]
    con = [i for i, it in enumerate(evidence) if it.relation == "contradicts"]
    best_e = max(range(len(evidence)), key=lambda i: evidence[i].nli.entailment)
    best_c = max(range(len(evidence)), key=lambda i: evidence[i].nli.contradiction)
    max_e, max_c = evidence[best_e].nli.entailment, evidence[best_c].nli.contradiction
    reasons: list[str] = []

    # ---- conflicting sources: refuse to force a verdict
    if sup and con:
        top_s = max(sup, key=lambda i: evidence[i].nli.entailment)
        top_c = max(con, key=lambda i: evidence[i].nli.contradiction)
        reasons.append("conflicting_evidence")
        return Verdict(
            status=STATUS_INSUFFICIENT, confidence=0.0, scores=evidence[top_s].nli, decisive_index=None, conflict=True,
            needs_review=True, review_reasons=reasons, evidence=evidence, supporting=sup, contradicting=con,
            explanation=(
                f"The sources disagree. {_src(evidence[top_s])} supports the claim "
                f"(entailment {evidence[top_s].nli.entailment:.0%}), while {_src(evidence[top_c])} contradicts it "
                f"(contradiction {evidence[top_c].nli.contradiction:.0%}). "
                "No verdict is forced; a person should decide which source to trust."
            ),
        )

    if sup:
        d = max(sup, key=lambda i: evidence[i].nli.entailment)
        conf = evidence[d].nli.entailment
        if conf < cfg.review_threshold:
            reasons.append("low_confidence")
        extra = f" {len(sup) - 1} other passage(s) also support it." if len(sup) > 1 else ""
        return Verdict(
            status=STATUS_SUPPORTED, confidence=conf, scores=evidence[d].nli, decisive_index=d, conflict=False,
            needs_review=bool(reasons), review_reasons=reasons, evidence=evidence, supporting=sup, contradicting=[],
            explanation=(f"{_src(evidence[d])} entails the claim (entailment {conf:.0%}, threshold "
                         f"{cfg.entail_threshold:.0%}).{extra}"
                         + (" Confidence is below the review threshold, so please double-check." if reasons else "")),
        )

    if con:
        d = max(con, key=lambda i: evidence[i].nli.contradiction)
        conf = evidence[d].nli.contradiction
        if conf < cfg.review_threshold:
            reasons.append("low_confidence")
        extra = f" {len(con) - 1} other passage(s) also contradict it." if len(con) > 1 else ""
        return Verdict(
            status=STATUS_CONTRADICTED, confidence=conf, scores=evidence[d].nli, decisive_index=d, conflict=False,
            needs_review=bool(reasons), review_reasons=reasons, evidence=evidence, supporting=[], contradicting=con,
            explanation=(f"{_src(evidence[d])} contradicts the claim (contradiction {conf:.0%}, threshold "
                         f"{cfg.contradict_threshold:.0%}).{extra}"
                         + (" Confidence is below the review threshold, so please double-check." if reasons else "")),
        )

    # ---- abstain: nothing decisive
    d = max(range(len(evidence)), key=lambda i: evidence[i].nli.neutral)
    near = max(max_e, max_c)
    if near >= cfg.near_miss_floor:
        reasons.append("near_threshold")
        which = "support" if max_e >= max_c else "contradiction"
        val = max_e if max_e >= max_c else max_c
        note = (f" The closest evidence leans toward {which} ({val:.0%}) but stays under the threshold, so a person "
                "should check it.")
    else:
        note = " The retrieved passages are on topic at best, but none says anything decisive about this claim."
    return Verdict(
        status=STATUS_INSUFFICIENT, confidence=evidence[d].nli.neutral, scores=evidence[d].nli, decisive_index=d,
        conflict=False, needs_review=bool(reasons), review_reasons=reasons, evidence=evidence, supporting=[],
        contradicting=[],
        explanation="The trusted documents do not contain enough evidence to support or contradict this claim." + note,
    )


def summarize(claim_results: list[dict]) -> dict:
    """Session-level summary computed from claim results."""
    total = len(claim_results)
    counts = {STATUS_SUPPORTED: 0, STATUS_CONTRADICTED: 0, STATUS_INSUFFICIENT: 0}
    review = conflicts = 0
    for c in claim_results:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
        review += 1 if c.get("needs_review") else 0
        conflicts += 1 if c.get("conflict") else 0
    sup, con, ins = counts[STATUS_SUPPORTED], counts[STATUS_CONTRADICTED], counts[STATUS_INSUFFICIENT]
    if total == 0:
        verdict, text = "no_claims", "No checkable factual claims were found in the answer."
    elif con > 0:
        verdict = "contains_contradictions"
        text = (f"{con} of {total} claims are contradicted by the trusted documents. "
                f"{sup} supported, {ins} could not be verified. Do not rely on this answer without correction.")
    elif sup == total:
        verdict = "fully_supported"
        text = f"All {total} claims are supported by the trusted documents."
    elif sup / total >= 0.6:
        verdict = "mostly_supported"
        text = f"{sup} of {total} claims are supported; {ins} lack sufficient evidence and need checking elsewhere."
    else:
        verdict = "insufficient_grounding"
        text = (f"Only {sup} of {total} claims are supported by the trusted documents; "
                f"{ins} lack sufficient evidence. The documents may not cover this topic.")
    if review:
        text += f" {review} claim(s) are flagged for human review."
    return {
        "total_claims": total, "supported": sup, "contradicted": con, "insufficient": ins,
        "needs_review": review, "conflicts": conflicts, "verdict": verdict, "overall": text,
        "supported_pct": round(100 * sup / total, 1) if total else 0.0,
        "contradicted_pct": round(100 * con / total, 1) if total else 0.0,
        "insufficient_pct": round(100 * ins / total, 1) if total else 0.0,
    }
