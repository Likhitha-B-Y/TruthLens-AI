"""Health, model status, settings, dashboard stats and sample data."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..config import APP_NAME, APP_VERSION, EMBEDDING_MODEL_CHOICES, NLI_MODEL_CHOICES, RuntimeSettings
from ..services.library import ingest_file, rebuild_index_async
from ..services.pipeline import Services
from .deps import get_services

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(svc: Services = Depends(get_services)):
    m = svc.models.snapshot()
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "models_ready": m["ready"],
            "nli_state": m["nli"]["state"], "embedding_state": m["embedding"]["state"]}


@router.get("/models/status")
def models_status(svc: Services = Depends(get_services)):
    return {**svc.models.snapshot(), "index": svc.index.info,
            "choices": {"nli": NLI_MODEL_CHOICES, "embedding": EMBEDDING_MODEL_CHOICES}}


@router.post("/models/reload")
def models_reload(svc: Services = Depends(get_services)):
    svc.models.start_background()
    return svc.models.snapshot()


@router.get("/settings")
def get_settings(svc: Services = Depends(get_services)):
    return {"settings": svc.settings.get().model_dump(),
            "choices": {"nli": NLI_MODEL_CHOICES, "embedding": EMBEDDING_MODEL_CHOICES}}


@router.put("/settings")
def put_settings(patch: dict, svc: Services = Depends(get_services)):
    unknown = set(patch) - set(RuntimeSettings.model_fields)
    if unknown:
        raise HTTPException(422, f"Unknown setting(s): {', '.join(sorted(unknown))}")
    old = svc.settings.get()
    new = svc.settings.update(patch)                       # pydantic validation errors -> 422
    reload_models = old.model_fields_requiring_reload() != new.model_fields_requiring_reload()
    chunk_changed = old.chunk_signature() != new.chunk_signature()
    if reload_models:
        svc.models.start_background()
    if chunk_changed or reload_models:
        svc.index.mark_dirty()
        if not reload_models:
            rebuild_index_async(svc)
    return {"settings": new.model_dump(), "models_reloading": reload_models, "reindexing": chunk_changed}


@router.post("/settings/reset")
def reset_settings(svc: Services = Depends(get_services)):
    old = svc.settings.get()
    new = svc.settings.reset()
    if old.model_fields_requiring_reload() != new.model_fields_requiring_reload():
        svc.models.start_background()
    svc.index.mark_dirty()
    return {"settings": new.model_dump()}


@router.get("/stats/overview")
def overview(svc: Services = Depends(get_services)):
    sessions = svc.db.list_sessions(limit=1000)
    done = [s for s in sessions if s["status"] == "completed"]
    agg = {"supported": 0, "contradicted": 0, "insufficient": 0, "total_claims": 0, "needs_review": 0}
    for s in done:
        for k in agg:
            agg[k] += int(s["summary"].get(k, 0))
    times = [s["processing_time"] for s in done if s.get("processing_time")]
    docs = svc.db.list_documents()
    return {
        "sessions": len(sessions), "completed": len(done), "documents": len(docs),
        "passages": sum(d["passage_count"] for d in docs), "claims": agg,
        "avg_processing_time": round(sum(times) / len(times), 2) if times else None,
        "recent": sessions[:6],
        "models": svc.models.snapshot(),
    }


# ----------------------------------------------------------------------- samples
def _samples_dir(svc: Services) -> Path:
    return svc.paths.samples


@router.get("/samples")
def samples(svc: Services = Depends(get_services)):
    d = _samples_dir(svc)
    answers_file = d / "sample_answers.json"
    payload = json.loads(answers_file.read_text(encoding="utf-8")) if answers_file.exists() else {}
    answers, note = payload.get("answers", []), payload.get("note", "")
    docs = sorted(p.name for p in d.iterdir() if p.suffix.lower() in {".pdf", ".docx", ".txt"}) if d.exists() else []
    return {"documents": docs, "answers": answers, "note": note}


@router.post("/samples/load")
def load_samples(svc: Services = Depends(get_services)):
    d = _samples_dir(svc)
    if not d.exists():
        raise HTTPException(404, "Sample folder not found.")
    loaded, skipped = [], []
    for p in sorted(d.iterdir()):
        if p.suffix.lower() not in {".pdf", ".docx", ".txt"}:
            continue
        try:
            doc, created = ingest_file(svc, p, p.name, is_sample=True)
            (loaded if created else skipped).append(doc["name"])
        except Exception as e:  # keep going; report per file
            skipped.append(f"{p.name} ({e})")
    if loaded:
        rebuild_index_async(svc)
    return {"loaded": loaded, "skipped": skipped}
