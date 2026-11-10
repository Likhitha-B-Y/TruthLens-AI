"""Claim extraction, verification, history and PDF report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from ..schemas import ExtractRequest, VerifyRequest
from ..services.claim_extraction import extract_claims
from ..services.pipeline import Services, start_verification
from ..services.report import build_report
from .deps import get_services

router = APIRouter(prefix="/api", tags=["verification"])


@router.post("/claims/extract")
def extract(req: ExtractRequest, svc: Services = Depends(get_services)):
    s = svc.settings.get()
    claims = extract_claims(
        req.answer,
        split_compound=s.split_compound if req.split_compound is None else req.split_compound,
        resolve_pronouns=s.resolve_pronouns if req.resolve_pronouns is None else req.resolve_pronouns,
        max_claims=req.max_claims or s.max_claims,
    )
    return {"claims": [c.to_dict() for c in claims], "count": len(claims)}


@router.post("/verify", status_code=202)
def verify(req: VerifyRequest, response: Response, svc: Services = Depends(get_services)):
    """Start a verification session. Poll GET /api/history/{id} until status is completed/failed.
    With `wait=true` the request blocks and returns the finished session (200)."""
    claims = [c.model_dump(exclude_none=True) for c in req.claims] if req.claims else None
    session = start_verification(svc, req.answer, claims, req.document_ids, wait=req.wait)
    if req.wait:
        response.status_code = 200
    return session


@router.get("/history")
def history(svc: Services = Depends(get_services)):
    sessions = svc.db.list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/history/{session_id}")
def get_session(session_id: str, svc: Services = Depends(get_services)):
    s = svc.db.get_session(session_id)
    if not s:
        raise HTTPException(404, "Verification session not found.")
    return s


@router.delete("/history/{session_id}")
def delete_session(session_id: str, svc: Services = Depends(get_services)):
    if not svc.db.delete_session(session_id):
        raise HTTPException(404, "Verification session not found.")
    return {"deleted": session_id}


@router.delete("/history")
def clear_history(svc: Services = Depends(get_services)):
    return {"deleted": svc.db.delete_all_sessions()}


@router.get("/history/{session_id}/report.pdf")
def report(session_id: str, svc: Services = Depends(get_services)):
    s = svc.db.get_session(session_id)
    if not s:
        raise HTTPException(404, "Verification session not found.")
    if s["status"] != "completed":
        raise HTTPException(409, "The report is available once verification has completed.")
    pdf = build_report(s)
    try:                                              # keep a copy in /reports for convenience
        (svc.paths.reports / f"TruthLens-report-{session_id}.pdf").write_bytes(pdf)
    except OSError:
        pass
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="TruthLens-report-{session_id}.pdf"'})
