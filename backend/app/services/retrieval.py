"""Hybrid evidence retrieval: BM25 (lexical) + FAISS (dense) fused with weighted reciprocal-rank fusion.

Retrieval only *finds candidate evidence*. Whether the evidence supports a claim is decided later by NLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from .text_utils import tokenize


@dataclass
class PassageRecord:
    id: int
    doc_id: int
    doc_name: str
    page: int
    idx: int
    text: str
    text_hash: str = ""
    meta: dict = field(default_factory=dict)       # free-form (used by FEVER evaluation)


@dataclass
class RetrievedPassage:
    passage: PassageRecord
    bm25_score: float | None = None
    bm25_rank: int | None = None
    dense_score: float | None = None
    dense_rank: int | None = None
    fused_score: float = 0.0
    fused_rank: int = 0

    def to_dict(self) -> dict:
        p = self.passage
        return {
            "passage_id": p.id, "doc_id": p.doc_id, "doc_name": p.doc_name, "page": p.page, "text": p.text,
            "bm25_score": _r(self.bm25_score), "bm25_rank": self.bm25_rank,
            "dense_score": _r(self.dense_score), "dense_rank": self.dense_rank,
            "fused_score": _r(self.fused_score, 5), "rank": self.fused_rank,
        }


def _r(v: float | None, nd: int = 4) -> float | None:
    return None if v is None else round(float(v), nd)


def _near_duplicate(a: set[str], b: set[str], thr: float = 0.9) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= thr


class HybridRetriever:
    """Immutable-after-build retriever over a fixed list of passages."""

    def __init__(self, passages: list[PassageRecord], embeddings: np.ndarray | None, embedder):
        self.passages = passages
        self.embedder = embedder
        self._tokens = [tokenize(p.text) for p in passages]
        # BM25Okapi cannot handle an empty token list per doc; keep a placeholder token
        corpus = [t if t else ["<empty>"] for t in self._tokens]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._token_sets = [set(t) for t in self._tokens]
        self._index = None
        self._dim = 0
        if embeddings is not None and len(embeddings):
            self._dim = int(embeddings.shape[1])
            self._index = faiss.IndexFlatIP(self._dim)           # cosine on L2-normalised vectors
            self._index.add(np.ascontiguousarray(embeddings, dtype=np.float32))
        self._doc_ids = np.array([p.doc_id for p in passages]) if passages else np.array([])

    @property
    def size(self) -> int:
        return len(self.passages)

    # ---- individual retrievers ---------------------------------------------------------
    def _mask(self, doc_ids: set[int] | None) -> np.ndarray | None:
        if not doc_ids:
            return None
        return np.isin(self._doc_ids, list(doc_ids))

    def search_bm25(self, query: str, k: int, doc_ids: set[int] | None = None) -> list[tuple[int, float]]:
        if not self.size or self._bm25 is None:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = np.asarray(self._bm25.get_scores(q), dtype=np.float64)
        mask = self._mask(doc_ids)
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        order = np.argsort(-scores)[:k]
        # keep only passages that share at least one query term
        return [(int(i), float(scores[i])) for i in order
                if np.isfinite(scores[i]) and (self._token_sets[i] & set(q))]

    def search_dense(self, query: str, k: int, doc_ids: set[int] | None = None) -> list[tuple[int, float]]:
        if self._index is None or not self.size:
            return []
        qv = self.embedder.encode([query], is_query=True)
        if qv.shape[1] != self._dim:
            return []
        mask = self._mask(doc_ids)
        kk = self.size if mask is not None else min(k, self.size)
        sims, ids = self._index.search(np.ascontiguousarray(qv, dtype=np.float32), kk)
        out: list[tuple[int, float]] = []
        for i, s in zip(ids[0], sims[0]):
            if i < 0:
                continue
            if mask is not None and not mask[i]:
                continue
            out.append((int(i), float(s)))
            if len(out) >= k:
                break
        return out

    # ---- fusion -------------------------------------------------------------------------
    def search(self, query: str, top_k: int = 5, *, bm25_candidates: int = 20, dense_candidates: int = 20,
               rrf_k: int = 60, bm25_weight: float = 1.0, dense_weight: float = 1.0,
               doc_ids: set[int] | None = None) -> list[RetrievedPassage]:
        bm = self.search_bm25(query, bm25_candidates, doc_ids)
        de = self.search_dense(query, dense_candidates, doc_ids)
        return self.fuse(bm, de, top_k, rrf_k=rrf_k, bm25_weight=bm25_weight, dense_weight=dense_weight)

    def fuse(self, bm: list[tuple[int, float]], de: list[tuple[int, float]], top_k: int, *, rrf_k: int = 60,
             bm25_weight: float = 1.0, dense_weight: float = 1.0) -> list[RetrievedPassage]:
        cands: dict[int, RetrievedPassage] = {}
        for rank, (i, s) in enumerate(bm, start=1):
            rp = cands.setdefault(i, RetrievedPassage(self.passages[i]))
            rp.bm25_score, rp.bm25_rank = s, rank
            rp.fused_score += bm25_weight / (rrf_k + rank)
        for rank, (i, s) in enumerate(de, start=1):
            rp = cands.setdefault(i, RetrievedPassage(self.passages[i]))
            rp.dense_score, rp.dense_rank = s, rank
            rp.fused_score += dense_weight / (rrf_k + rank)
        ranked = sorted(cands.items(), key=lambda kv: (-kv[1].fused_score, kv[0]))
        # de-duplicate: identical text hash or near-identical token sets (overlapping chunks, repeated text)
        out: list[RetrievedPassage] = []
        seen_hashes: set[str] = set()
        kept_sets: list[set[str]] = []
        for i, rp in ranked:
            h = rp.passage.text_hash or rp.passage.text
            if h in seen_hashes:
                continue
            ts = self._token_sets[i]
            if any(_near_duplicate(ts, other) for other in kept_sets):
                continue
            seen_hashes.add(h)
            kept_sets.append(ts)
            rp.fused_rank = len(out) + 1
            out.append(rp)
            if len(out) >= top_k:
                break
        return out
