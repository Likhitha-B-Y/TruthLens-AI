import json

import pytest

from app.config import RuntimeSettings, STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED
from app.evaluation import metrics as M
from app.evaluation.baselines import dense_classify, has_negation, keyword_classify, keyword_features, nli_argmax_classify
from app.evaluation.fever import (FeverDataError, build_passages, collect_pages, discover_fever_files, load_claims,
                                  parse_lines, readable_title)
from app.evaluation.runner import EvalConfig, run_evaluation, run_evaluation_core
from app.services.embeddings import TfidfLsaEmbedder
from app.services.nli import NLIScores
from fever_fixture import make_fever
from helpers import StubNLI

S, C, I = STATUS_SUPPORTED, STATUS_CONTRADICTED, STATUS_INSUFFICIENT


# ----------------------------------------------------------------- metrics (hand-computed)
def test_classification_metrics_against_hand_computation():
    gold = [S, S, C, C, I, I]
    pred = [S, C, C, C, I, S]
    m = M.classification_metrics(gold, pred)
    assert m["accuracy"] == pytest.approx(4 / 6)
    # per class: S p=1/2 r=1/2 ; C p=2/3 r=1 ; I p=1 r=1/2
    assert m["per_class"][S]["precision"] == pytest.approx(0.5) and m["per_class"][S]["recall"] == pytest.approx(0.5)
    assert m["per_class"][C]["precision"] == pytest.approx(2 / 3) and m["per_class"][C]["recall"] == pytest.approx(1.0)
    assert m["per_class"][I]["precision"] == pytest.approx(1.0) and m["per_class"][I]["recall"] == pytest.approx(0.5)
    f = [0.5, 0.8, 2 / 3]
    assert m["macro_f1"] == pytest.approx(sum(f) / 3)
    assert m["confusion_matrix"]["matrix"] == [[1, 1, 0], [0, 2, 0], [1, 0, 1]]


def test_abstention_metrics():
    gold = [S, C, I, I, S, I]
    pred = [S, S, I, I, I, S]
    a = M.abstention_metrics(gold, pred)
    assert a["coverage"] == pytest.approx(3 / 6)               # answered: idx0, idx1, idx5
    assert a["selective_error_rate"] == pytest.approx(2 / 3)   # idx1 and idx5 wrong
    assert a["abstain_precision"] == pytest.approx(2 / 3)      # abstained idx2, idx3, idx4 -> 2 truly NEI
    assert a["abstain_recall"] == pytest.approx(2 / 3)


def meta(page, *sents):
    return {"page_id": page, "sent_ids": list(sents)}


def test_retrieval_metrics_recall_precision_at_k():
    items = [
        {"verifiable": True, "gold_groups": [[("A", 1)]], "retrieved_meta": [meta("B", 0), meta("A", 0, 1, 2), meta("C", 5)]},
        {"verifiable": True, "gold_groups": [[("X", 0), ("Y", 3)]], "retrieved_meta": [meta("X", 0), meta("Z", 1), meta("Y", 3)]},
        {"verifiable": False, "gold_groups": [], "retrieved_meta": [meta("Q", 0)]},          # NEI is ignored
    ]
    r = M.retrieval_metrics(items, [1, 3])
    assert r["n_verifiable"] == 2
    assert r["recall@1"] == pytest.approx(0.0)          # nothing fully covered at k=1 (claim 2 needs X and Y)
    assert r["hit@1"] == pytest.approx(0.5)             # claim 2's X0 hit
    assert r["recall@3"] == pytest.approx(1.0)
    assert r["precision@3"] == pytest.approx((1 / 3 + 2 / 3) / 2)


def test_citation_metrics():
    items = [
        {"gold": S, "pred": S, "gold_groups": [[("A", 1)]], "cited_meta": meta("A", 1)},      # correct + cited
        {"gold": S, "pred": S, "gold_groups": [[("A", 1)]], "cited_meta": meta("B", 1)},      # right label, wrong citation
        {"gold": I, "pred": S, "gold_groups": [], "cited_meta": meta("A", 1)},                # false answer on NEI
        {"gold": I, "pred": I, "gold_groups": [], "cited_meta": None},                         # correct abstention
    ]
    c = M.citation_metrics(items)
    assert c["citation_correctness"] == pytest.approx(1 / 3)
    assert c["fever_style_score"] == pytest.approx(2 / 4)


# ---------------------------------------------------------------------------- baselines
def test_keyword_baseline_rules():
    f = keyword_features("The tower is not tall", ["The tower is tall and old."])
    assert f[0] > 0.5 and f[1] is True
    assert keyword_classify(f, 0.8, 0.6)[0] == C
    f2 = keyword_features("The tower is tall", ["The tower is tall and old."])
    assert keyword_classify(f2, 0.8, 0.6)[0] == S
    f3 = keyword_features("Bananas grow in Peru", ["The tower is tall and old."])
    assert keyword_classify(f3, 0.8, 0.6)[0] == I
    assert has_negation("It isn't there") and not has_negation("It is there")


def test_dense_baseline_never_predicts_contradiction():
    assert dense_classify(0.9, 0.5) == S and dense_classify(0.2, 0.5) == I and dense_classify(None, 0.5) == I


def test_nli_argmax_baseline():
    lab, idx = nli_argmax_classify([NLIScores(0.1, 0.1, 0.8), NLIScores(0.1, 0.8, 0.1)])
    assert (lab, idx) == (C, 1)
    assert nli_argmax_classify([])[0] == I


# -------------------------------------------------------------------------- data loading
def test_fever_loading_pipeline(tmp_path):
    claims_file, wiki = make_fever(tmp_path)
    claims = load_claims(claims_file, 30, seed=3)
    assert len(claims) == 30 and {c.label for c in claims} == {S, C, I}
    assert sum(1 for c in claims if c.label == S) == 10
    assert all(c.gold_groups for c in claims if c.label != I) and all(not c.gold_groups for c in claims if c.label == I)
    needed = {p for c in claims for g in c.gold_groups for p, _ in g}
    pages = collect_pages(wiki, needed, distractors=10, seed=3)
    assert needed <= set(pages) and len(pages) > len(needed)
    passages = build_passages(pages, window=3)
    assert all(p.text.startswith(p.doc_name + ":") for p in passages)
    # every sentence of every page is covered by at least one passage
    for pid, sents in pages.items():
        covered = {i for p in passages if p.meta["page_id"] == pid for i in p.meta["sent_ids"]}
        assert covered == {i for i, _ in sents}
    found = discover_fever_files(tmp_path.parent)
    assert found["ready"] is False


def test_fever_helpers_and_errors(tmp_path):
    assert parse_lines("0\tHello world.\tlink\n1\t\n2\tSecond.") == [(0, "Hello world."), (2, "Second.")]
    assert readable_title("Nikolaj_Coster-Waldau_-LRB-actor-RRB-") == "Nikolaj Coster-Waldau (actor)"
    with pytest.raises(FeverDataError):
        load_claims(tmp_path / "missing.jsonl", 30)
    claims_file, _ = make_fever(tmp_path, n_entities=2)
    with pytest.raises(FeverDataError):
        load_claims(claims_file, 300)       # not enough claims per label


def test_discover_files(tmp_path):
    claims_file, wiki = make_fever(tmp_path)
    d = tmp_path / "evaluation"
    (d / "data" / "fever").mkdir(parents=True)
    (d / "data" / "fever" / "shared_task_dev.jsonl").write_text(claims_file.read_text())
    (d / "data" / "fever" / "wiki-pages").mkdir()
    (d / "data" / "fever" / "wiki-pages" / "wiki-001.jsonl").write_text("{}\n")
    f = discover_fever_files(d)
    assert f["ready"] and f["claims_file"].endswith("shared_task_dev.jsonl")


# ---------------------------------------------------------------------------- full runner
def run_core(tmp_path, n_entities, sample, calib):
    claims_file, wiki = make_fever(tmp_path, n_entities=n_entities)
    cfg = EvalConfig(str(claims_file), str(wiki), sample_size=sample, top_k=3, window=3, distractors=20,
                     calibration_fraction=calib, seed=5)
    claims = load_claims(claims_file, sample, 5)
    needed = {p for c in claims for g in c.gold_groups for p, _ in g}
    pages = collect_pages(wiki, needed, 20, 5)
    stages = []
    res = run_evaluation_core(cfg, StubNLI(), TfidfLsaEmbedder(), RuntimeSettings(), claims, pages,
                              lambda s, d, t: stages.append(s))
    return res, stages


def test_runner_with_calibration_split(tmp_path):
    res, stages = run_core(tmp_path, 20, 60, 0.5)
    assert {"embedding_corpus", "retrieving", "nli_inference"} <= set(stages)
    assert set(res["methods"]) == {"bm25_keyword", "dense_similarity", "retrieval_nli", "proposed"}
    assert res["dataset"]["calibration"]["n"] == 30 and res["dataset"]["test"]["n"] == 30
    assert res["dataset"]["calibration"]["n"] + res["dataset"]["test"]["n"] == 60
    for key, m in res["methods"].items():
        mm = m["metrics"]
        assert 0 <= mm["accuracy"] <= 1 and 0 <= mm["macro_f1"] <= 1 and mm["n"] == 30
        assert sum(sum(r) for r in mm["confusion_matrix"]["matrix"]) == 30
        assert m["timing"]["total_s_per_claim"] >= 0 and "coverage" in m["abstention"]
    assert res["methods"]["bm25_keyword"]["tuned_on_calibration"] and res["methods"]["proposed"]["tuned_on_calibration"]
    assert not res["methods"]["retrieval_nli"]["tuned_on_calibration"]
    assert res["methods"]["dense_similarity"]["metrics"]["per_class"][C]["recall"] == 0.0    # cannot predict contradiction
    for r in res["retrieval"].values():
        assert 0 <= r["recall@3"] <= 1 and r["recall@1"] <= r["recall@3"] + 1e-9
    assert res["retrieval"]["bm25"]["n_verifiable"] == 20
    assert any("closed subset" in n.lower() for n in res["notes"]) and any("tuned" in n for n in res["notes"])
    assert len(res["examples"]) == 30
    json.dumps(res)                                          # must be JSON-serialisable for storage


def test_runner_small_sample_skips_tuning(tmp_path):
    res, _ = run_core(tmp_path, 6, 9, 0.2)
    assert not res["methods"]["proposed"]["tuned_on_calibration"]
    assert any("too small" in n for n in res["notes"])


def test_runner_flags_fever_trained_model(tmp_path):
    claims_file, wiki = make_fever(tmp_path, n_entities=6)
    claims = load_claims(claims_file, 9, 5)
    pages = collect_pages(wiki, {p for c in claims for g in c.gold_groups for p, _ in g}, 5, 5)
    nli = StubNLI(); nli.model_name = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    res = run_evaluation_core(EvalConfig(sample_size=9, top_k=3), nli, TfidfLsaEmbedder(), RuntimeSettings(), claims, pages)
    assert any("leakage" in n for n in res["notes"])


def test_background_evaluation_job_end_to_end(loaded_client, tmp_path):
    svc = loaded_client.app.state.services
    claims_file, wiki = make_fever(tmp_path, n_entities=6)
    cfg = EvalConfig(str(claims_file), str(wiki), sample_size=9, top_k=3, distractors=5, calibration_fraction=0.2, seed=2)
    rid = svc.db.create_eval_run(cfg.__dict__)
    run_evaluation(svc, rid, cfg)
    run = loaded_client.get(f"/api/evaluation/runs/{rid}").json()
    assert run["status"] == "completed", run.get("error")
    latest = loaded_client.get("/api/evaluation/results").json()
    assert latest["id"] == rid and "proposed" in latest["results"]["methods"]
    assert (svc.paths.evaluation / "results" / "latest.json").exists()
    bad = svc.db.create_eval_run({})
    run_evaluation(svc, bad, EvalConfig("/nope.jsonl", "/nope"))
    assert loaded_client.get(f"/api/evaluation/runs/{bad}").json()["status"] == "failed"
