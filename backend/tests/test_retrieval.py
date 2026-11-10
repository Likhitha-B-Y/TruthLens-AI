import numpy as np
import pytest

from app.services.document_processing import chunk_pages, extract_document
from app.services.embeddings import TfidfLsaEmbedder
from app.services.retrieval import HybridRetriever, PassageRecord
from conftest import SAMPLES


@pytest.fixture(scope="module")
def retriever():
    passages = []
    for doc_id, fname in enumerate(["eiffel_tower_factsheet.txt", "photosynthesis_overview.docx", "solar_system_notes.pdf"], 1):
        d = extract_document(SAMPLES / fname)
        for dr in chunk_pages(d.pages, chunk_words=40, overlap_sentences=1):
            passages.append(PassageRecord(len(passages), doc_id, fname, dr.page, dr.idx, dr.text, dr.text_hash))
    emb = TfidfLsaEmbedder(n_components=32)
    emb.fit([p.text for p in passages])
    return HybridRetriever(passages, emb.encode([p.text for p in passages]), emb)


def test_bm25_finds_lexical_match(retriever):
    hits = retriever.search_bm25("How tall is the Eiffel Tower in metres", 3)
    assert hits and "330 metres" in retriever.passages[hits[0][0]].text


def test_bm25_ignores_passages_without_query_terms(retriever):
    assert retriever.search_bm25("xylophone zeppelin quasar", 5) == []


def test_dense_retrieval_returns_scores_in_range(retriever):
    hits = retriever.search_dense("chlorophyll absorbs light in chloroplasts", 3)
    assert hits and "chlorophyll" in retriever.passages[hits[0][0]].text.lower()
    assert all(-1.001 <= s <= 1.001 for _, s in hits)
    assert [s for _, s in hits] == sorted([s for _, s in hits], reverse=True)


def test_hybrid_fusion_exposes_both_scores_and_ranks(retriever):
    res = retriever.search("The planet Venus is the hottest", top_k=3)
    assert res and res[0].fused_rank == 1
    top = res[0]
    assert "Venus" in top.passage.text
    assert top.bm25_score is not None and top.dense_score is not None
    assert top.fused_score > 0
    assert [r.fused_score for r in res] == sorted([r.fused_score for r in res], reverse=True)


def test_hybrid_removes_duplicates(retriever):
    res = retriever.search("Eiffel Tower", top_k=10)
    assert len({r.passage.id for r in res}) == len(res)
    assert len({r.passage.text_hash for r in res}) == len(res)


def test_fusion_gives_credit_to_passages_found_by_both_retrievers(retriever):
    both = retriever.fuse([(0, 5.0), (1, 4.0)], [(1, 0.9), (2, 0.8)], top_k=3)
    assert both[0].passage.id == 1            # appears in both lists -> highest RRF score


def test_weights_change_ranking(retriever):
    bm_only = retriever.fuse([(0, 5.0)], [(1, 0.9)], 2, bm25_weight=1.0, dense_weight=0.0)
    de_only = retriever.fuse([(0, 5.0)], [(1, 0.9)], 2, bm25_weight=0.0, dense_weight=1.0)
    assert bm_only[0].passage.id == 0 and de_only[0].passage.id == 1


def test_document_filter(retriever):
    res = retriever.search("planet", top_k=5, doc_ids={3})
    assert res and all(r.passage.doc_id == 3 for r in res)
    assert retriever.search("planet", top_k=5, doc_ids={99}) == []


def test_empty_retriever_is_safe():
    r = HybridRetriever([], None, TfidfLsaEmbedder())
    assert r.search("anything") == []
