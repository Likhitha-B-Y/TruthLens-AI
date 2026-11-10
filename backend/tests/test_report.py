import fitz

from app.services.report import build_report


def session(claims):
    return {
        "id": "abc123", "created_at": "2026-11-03T10:00:00+00:00", "status": "completed",
        "answer_text": "Unicode test: café, naïve, “quotes”, <b>tags</b> & ampersands.\nSecond line.",
        "summary": {"total_claims": len(claims), "supported": 1, "contradicted": 1, "insufficient": 1, "needs_review": 1,
                    "overall": "1 of 3 supported & <ok>.", "processing_time": 2.5,
                    "documents_used": [{"id": 1, "name": "doc <1>.pdf"}],
                    "models": {"nli": "m", "embedding": "e", "embedding_backend": "sentence-transformers"}},
        "claims": claims,
    }


def claim(i, status, review=False):
    return {"id": f"C{i}", "text": f"Claim {i} with <special> & chars é", "status": status, "confidence": 0.91,
            "scores": {"entailment": 0.91, "contradiction": 0.05, "neutral": 0.04},
            "explanation": "Because & <reasons>.", "needs_review": review, "review_reasons": ["low_confidence"] if review else [],
            "evidence": [{"doc_name": "doc <1>.pdf", "page": 3, "text": "Evidence text with é and & symbols.", "rank": 1,
                          "bm25_score": 4.2, "dense_score": 0.77, "relation": "supports",
                          "nli": {"entailment": 0.91, "contradiction": 0.05, "neutral": 0.04}}]}


def test_report_contains_all_sections():
    pdf = build_report(session([claim(1, "SUPPORTED"), claim(2, "CONTRADICTED", True), claim(3, "INSUFFICIENT_EVIDENCE")]))
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    for needle in ("TruthLens AI", "Verification summary", "Original AI-generated answer", "Claim-by-claim", "SUPPORTED",
                   "CONTRADICTED", "INSUFFICIENT EVIDENCE", "Human review recommended", "Limitations and disclaimer",
                   "page 3", "Entailment", "abc123"):
        assert needle in text, needle
    assert "Claim 2 with <special> & chars" in text          # escaped correctly, not interpreted as markup


def test_report_handles_many_claims_and_empty():
    many = [claim(i, "SUPPORTED") for i in range(40)]
    assert fitz.open(stream=build_report(session(many)), filetype="pdf").page_count >= 5
    assert build_report(session([]))[:5] == b"%PDF-"
