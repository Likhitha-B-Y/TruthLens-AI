import os

import pytest

from app.config import STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED
from app.services.aggregation import AggregationConfig, EvidenceItem, aggregate, classify_evidence, summarize
from app.services.embeddings import ModelLoadError
from app.services.nli import DebertaNLI, NLIScores
from helpers import StubNLI


def ev(e, c, n, doc="doc.pdf", page=1):
    return EvidenceItem(passage={"doc_name": doc, "page": page, "passage_id": 1, "text": "x"}, nli=NLIScores(e, c, n))


CFG = AggregationConfig()


# ------------------------------------------------------------------ NLI plumbing
def test_label_index_mapping_follows_model_config():
    cross = DebertaNLI._label_indices({0: "contradiction", 1: "entailment", 2: "neutral"})
    moritz = DebertaNLI._label_indices({0: "entailment", 1: "neutral", 2: "contradiction"})
    assert cross == {"contradiction": 0, "entailment": 1, "neutral": 2}
    assert moritz == {"entailment": 0, "neutral": 1, "contradiction": 2}
    assert DebertaNLI._label_indices({0: "CONTRADICTION", 1: "ENTAILMENT", 2: "NEUTRAL"})["entailment"] == 1


def test_non_nli_model_is_rejected():
    with pytest.raises(ModelLoadError):
        DebertaNLI._label_indices({0: "positive", 1: "negative"})


def test_model_load_failure_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(ModelLoadError):
        DebertaNLI("definitely/not-a-real-model-xyz").load()


def test_scores_argmax_and_rounding():
    s = NLIScores(0.2, 0.7, 0.1)
    assert s.argmax == "contradiction" and s.to_dict()["contradiction"] == 0.7


def test_stub_nli_is_deterministic_and_normalised():
    out = StubNLI().predict(["The tower is 330 metres tall."], ["The tower is 150 metres tall."])
    assert out[0].contradiction > 0.9 and abs(sum([out[0].entailment, out[0].contradiction, out[0].neutral]) - 1) < 1e-6


@pytest.mark.skipif(os.environ.get("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1 to test the real DeBERTa model")
def test_real_deberta_model_three_way():
    nli = DebertaNLI("cross-encoder/nli-deberta-v3-xsmall", "cpu", 4)
    nli.load()
    s = nli.predict(["The Eiffel Tower is 330 metres tall and stands in Paris."] * 3,
                    ["The Eiffel Tower is in Paris.", "The Eiffel Tower is in Rome.", "The Eiffel Tower has a restaurant."])
    assert s[0].argmax == "entailment" and s[1].argmax == "contradiction" and s[2].argmax == "neutral"


# ------------------------------------------------------------------- aggregation
def test_supported_when_entailment_above_threshold():
    v = aggregate([ev(0.92, 0.03, 0.05)], CFG)
    assert v.status == STATUS_SUPPORTED and v.decisive_index == 0 and not v.needs_review
    assert "entails" in v.explanation


def test_contradicted_when_contradiction_above_threshold():
    v = aggregate([ev(0.02, 0.95, 0.03)], CFG)
    assert v.status == STATUS_CONTRADICTED and v.confidence == pytest.approx(0.95)


def test_neutral_evidence_gives_insufficient():
    v = aggregate([ev(0.05, 0.05, 0.90), ev(0.2, 0.1, 0.7)], CFG)
    assert v.status == STATUS_INSUFFICIENT and not v.conflict and not v.needs_review


def test_no_evidence_abstains_and_requests_review():
    v = aggregate([], CFG)
    assert v.status == STATUS_INSUFFICIENT and v.needs_review and "no_evidence_retrieved" in v.review_reasons


def test_abstains_when_below_threshold_and_flags_near_miss():
    v = aggregate([ev(0.62, 0.05, 0.33)], CFG)
    assert v.status == STATUS_INSUFFICIENT and "near_threshold" in v.review_reasons and v.needs_review


def test_conflicting_sources_are_not_forced():
    v = aggregate([ev(0.93, 0.02, 0.05, "a.pdf", 2), ev(0.03, 0.94, 0.03, "b.pdf", 7)], CFG)
    assert v.status == STATUS_INSUFFICIENT and v.conflict and v.needs_review
    assert v.supporting == [0] and v.contradicting == [1]
    assert "a.pdf" in v.explanation and "b.pdf" in v.explanation and "disagree" in v.explanation


def test_confident_but_below_review_threshold_is_flagged():
    v = aggregate([ev(0.78, 0.02, 0.20)], CFG)
    assert v.status == STATUS_SUPPORTED and v.needs_review and "low_confidence" in v.review_reasons


def test_thresholds_are_configurable():
    items = lambda: [ev(0.78, 0.02, 0.20)]  # noqa: E731
    assert aggregate(items(), AggregationConfig(entail_threshold=0.9)).status == STATUS_INSUFFICIENT
    assert aggregate(items(), AggregationConfig(entail_threshold=0.6)).status == STATUS_SUPPORTED
    assert classify_evidence(NLIScores(0.55, 0.40, 0.05), AggregationConfig(entail_threshold=0.5, margin=0.2)) == "neutral"


def test_multiple_supporting_passages_mentioned():
    v = aggregate([ev(0.9, 0.05, 0.05), ev(0.95, 0.02, 0.03)], CFG)
    assert v.decisive_index == 1 and "1 other passage" in v.explanation


def test_summary_counts_and_overall_text():
    claims = [{"status": STATUS_SUPPORTED, "needs_review": False}, {"status": STATUS_CONTRADICTED, "needs_review": True},
              {"status": STATUS_INSUFFICIENT, "needs_review": True, "conflict": True}]
    s = summarize(claims)
    assert (s["total_claims"], s["supported"], s["contradicted"], s["insufficient"], s["needs_review"], s["conflicts"]) == (3, 1, 1, 1, 2, 1)
    assert s["verdict"] == "contains_contradictions" and "flagged for human review" in s["overall"]
    assert summarize([])["verdict"] == "no_claims"
    assert summarize([{"status": STATUS_SUPPORTED}] * 2)["verdict"] == "fully_supported"
