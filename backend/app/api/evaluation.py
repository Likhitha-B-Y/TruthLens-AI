"""FEVER evaluation endpoints (runs in a background thread)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import EvalRunRequest
from ..services.pipeline import Services
from .deps import get_services

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/status")
def status(svc: Services = Depends(get_services)):
    from ..evaluation.fever import discover_fever_files

    runs = svc.db.list_eval_runs(5)
    running = next((r for r in runs if r["status"] == "running"), None)
    latest = svc.db.latest_completed_eval()
    return {
        "data": discover_fever_files(svc.paths.evaluation),
        "running": running, "latest": latest,
        "setup_hint": "python evaluation/download_fever.py --split paper_dev",
    }


@router.post("/run", status_code=202)
def run(req: EvalRunRequest, svc: Services = Depends(get_services)):
    from ..evaluation.fever import discover_fever_files
    from ..evaluation.runner import EvalConfig, run_evaluation

    if any(r["status"] == "running" for r in svc.db.list_eval_runs(5)):
        raise HTTPException(409, "An evaluation is already running.")
    found = discover_fever_files(svc.paths.evaluation)
    fever = req.fever_path or found.get("claims_file")
    wiki = req.wiki_dir or found.get("wiki_dir")
    if not fever or not wiki:
        raise HTTPException(
            400,
            "FEVER data not found. Download it with `python evaluation/download_fever.py` "
            "(see evaluation/README.md) or provide fever_path and wiki_dir.")
    svc.models.require_nli()                               # fail fast if the NLI model is not available
    cfg = EvalConfig(fever_path=fever, wiki_dir=wiki, sample_size=req.sample_size, top_k=req.top_k,
                     window=req.window, distractors=req.distractors,
                     calibration_fraction=req.calibration_fraction, seed=req.seed)
    rid = svc.db.create_eval_run(cfg.__dict__)
    svc.eval_pool.submit(run_evaluation, svc, rid, cfg)
    return svc.db.get_eval_run(rid)


@router.get("/runs")
def runs(svc: Services = Depends(get_services)):
    return {"runs": svc.db.list_eval_runs(20)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, svc: Services = Depends(get_services)):
    r = svc.db.get_eval_run(run_id)
    if not r:
        raise HTTPException(404, "Evaluation run not found.")
    return r


@router.get("/results")
def results(svc: Services = Depends(get_services)):
    r = svc.db.latest_completed_eval()
    if not r:
        raise HTTPException(404, "No completed evaluation yet.")
    return r
