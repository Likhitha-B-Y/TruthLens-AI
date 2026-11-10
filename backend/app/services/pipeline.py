"""End-to-end verification pipeline + the service container shared by API routes."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..config import Paths, RuntimeSettings
from ..database import Database, utcnow
from .aggregation import AggregationConfig, EvidenceItem, aggregate, summarize
from .claim_extraction import Claim, claims_from_user, extract_claims
from .embeddings import ModelLoadError
from .managers import IndexManager, ModelManager, SettingsStore

log = logging.getLogger(__name__)


class VerificationError(Exception):
    """User-facing pipeline error (no documents, no claims ...)."""


@dataclass
class Services:
    paths: Paths
    db: Database
    settings: SettingsStore
    models: ModelManager
    index: IndexManager
    verify_pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=1, thread_name_prefix="verify"))
    eval_pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=1, thread_name_prefix="eval"))


def _title(answer: str) -> str:
    t = " ".join(answer.split())
    return (t[:64] + "...") if len(t) > 64 else t


def _order_evidence(items: list[EvidenceItem], verdict) -> list[dict]:
    """Decisive evidence first; for conflicts show the strongest support then the strongest contradiction."""
    def priority(i: int) -> tuple[int, int]:
        if verdict.conflict:
            top_s = max(verdict.supporting, key=lambda k: items[k].nli.entailment)
            top_c = max(verdict.contradicting, key=lambda k: items[k].nli.contradiction)
            if i == top_s:
                return (0, i)
            if i == top_c:
                return (1, i)
        elif verdict.decisive_index is not None and i == verdict.decisive_index:
            return (0, i)
        return (2, i)

    order = sorted(range(len(items)), key=priority)
    out = []
    for new_rank, i in enumerate(order):
        d = items[i].to_dict()
        d["primary"] = (new_rank == 0 and verdict.decisive_index is not None) or (verdict.conflict and new_rank < 2)
        out.append(d)
    return out


def claim_result(claim: Claim, verdict, retrieval_seconds: float) -> dict:
    return {
        **claim.to_dict(),
        "status": verdict.status,
        "confidence": round(verdict.confidence, 4),
        "scores": verdict.scores.to_dict() if verdict.scores else {"entailment": 0.0, "contradiction": 0.0, "neutral": 0.0},
        "explanation": verdict.explanation,
        "conflict": verdict.conflict,
        "needs_review": verdict.needs_review,
        "review_reasons": verdict.review_reasons,
        "evidence": _order_evidence(verdict.evidence, verdict),
        "retrieval_seconds": round(retrieval_seconds, 4),
    }


def run_verification(svc: Services, session_id: str, answer: str, claims_in: list[dict] | None,
                     doc_ids: list[int] | None) -> dict:
    """Execute a verification session synchronously and persist the result."""
    db = svc.db
    t_start = time.perf_counter()
    timings: dict[str, float] = {}

    def progress(stage: str, done: int, total: int) -> None:
        db.update_session(session_id, progress={"stage": stage, "done": done, "total": total})

    try:
        db.update_session(session_id, status="running")
        s: RuntimeSettings = svc.settings.get()

        # 1. claims ---------------------------------------------------------------------
        progress("extracting_claims", 0, 0)
        t = time.perf_counter()
        if claims_in:
            claims = claims_from_user(claims_in)
        else:
            claims = extract_claims(answer, split_compound=s.split_compound, resolve_pronouns=s.resolve_pronouns,
                                    max_claims=s.max_claims)
        timings["claim_extraction"] = time.perf_counter() - t
        if not claims:
            raise VerificationError("No checkable factual claims were found in the answer. "
                                    "Paste a longer answer or add claims manually.")

        # 2. documents / index ----------------------------------------------------------
        all_docs = db.list_documents()
        if not all_docs:
            raise VerificationError("The evidence library is empty. Upload at least one trusted document first.")
        wanted = set(doc_ids or [])
        if wanted:
            existing = {d["id"] for d in all_docs}
            missing = wanted - existing
            if missing:
                raise VerificationError(f"Selected document(s) no longer exist: {sorted(missing)}")
        used_docs = [d for d in all_docs if not wanted or d["id"] in wanted]
        progress("indexing", 0, 0)
        t = time.perf_counter()
        retriever = svc.index.get_retriever()
        timings["indexing"] = time.perf_counter() - t
        if retriever is None or retriever.size == 0:
            raise VerificationError("The selected documents contain no indexable passages.")

        # 3. hybrid retrieval -----------------------------------------------------------
        t = time.perf_counter()
        retrieved: list[list] = []
        per_claim_ret: list[float] = []
        for i, c in enumerate(claims):
            progress("retrieving_evidence", i, len(claims))
            t1 = time.perf_counter()
            retrieved.append(retriever.search(
                c.text, top_k=s.top_k, bm25_candidates=s.bm25_candidates, dense_candidates=s.dense_candidates,
                rrf_k=s.rrf_k, bm25_weight=s.bm25_weight, dense_weight=s.dense_weight, doc_ids=wanted or None))
            per_claim_ret.append(time.perf_counter() - t1)
        timings["retrieval"] = time.perf_counter() - t

        # 4. NLI over every (evidence, claim) pair -----------------------------------------
        nli = svc.models.require_nli()
        premises, hypotheses, owners = [], [], []
        for ci, (c, rps) in enumerate(zip(claims, retrieved)):
            for rp in rps[: s.nli_top_k]:
                premises.append(rp.passage.text)
                hypotheses.append(c.text)
                owners.append((ci, rp))
        t = time.perf_counter()
        total_pairs = len(premises)
        progress("verifying_with_nli", 0, total_pairs)
        last = {"t": 0.0}

        def cb(done: int, total: int) -> None:
            if time.perf_counter() - last["t"] > 0.4 or done == total:
                last["t"] = time.perf_counter()
                progress("verifying_with_nli", done, total)

        scores = nli.predict(premises, hypotheses, progress=cb) if total_pairs else []
        timings["nli"] = time.perf_counter() - t

        # 5. aggregation + abstention --------------------------------------------------------
        progress("aggregating", 0, len(claims))
        cfg = AggregationConfig.from_settings(s)
        per_claim: list[list[EvidenceItem]] = [[] for _ in claims]
        for (ci, rp), sc in zip(owners, scores):
            per_claim[ci].append(EvidenceItem(passage=rp.to_dict(), nli=sc))
        results = []
        for ci, c in enumerate(claims):
            verdict = aggregate(per_claim[ci], cfg)
            results.append(claim_result(c, verdict, per_claim_ret[ci]))

        total_time = time.perf_counter() - t_start
        summary = summarize(results)
        summary.update({
            "processing_time": round(total_time, 3),
            "timings": {k: round(v, 3) for k, v in timings.items()},
            "documents_used": [{"id": d["id"], "name": d["name"]} for d in used_docs],
            "nli_pairs": total_pairs,
            "models": {"nli": svc.models.status["nli"].get("model"),
                       "embedding": svc.models.status["embedding"].get("model"),
                       "embedding_backend": svc.models.status["embedding"].get("backend")},
        })
        db.update_session(session_id, status="completed", finished_at=utcnow(), claims=results, summary=summary,
                          processing_time=round(total_time, 3),
                          progress={"stage": "done", "done": len(claims), "total": len(claims)})
        log.info("Session %s done: %d claims, %d supported, %.1fs", session_id, len(claims),
                 summary["supported"], total_time)
        return db.get_session(session_id)  # type: ignore[return-value]

    except (VerificationError, ModelLoadError) as e:
        db.update_session(session_id, status="failed", finished_at=utcnow(), error=str(e))
        log.warning("Session %s failed: %s", session_id, e)
    except Exception as e:  # pragma: no cover - unexpected bug
        log.exception("Session %s crashed", session_id)
        db.update_session(session_id, status="failed", finished_at=utcnow(), error=f"Unexpected error: {e}")
    return db.get_session(session_id)  # type: ignore[return-value]


def start_verification(svc: Services, answer: str, claims_in: list[dict] | None, doc_ids: list[int] | None,
                       wait: bool = False) -> dict:
    s = svc.settings.get()
    sid = svc.db.create_session(answer_text=answer, document_ids=doc_ids or [], settings=s.model_dump(),
                                title=_title(answer))
    if wait:
        return run_verification(svc, sid, answer, claims_in, doc_ids)
    svc.verify_pool.submit(run_verification, svc, sid, answer, claims_in, doc_ids)
    return svc.db.get_session(sid)  # type: ignore[return-value]
