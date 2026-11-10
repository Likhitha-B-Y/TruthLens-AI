"""FastAPI application factory."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import APP_NAME, APP_VERSION, Paths, configure_hf_cache, configure_logging
from .database import Database
from .services.document_processing import DocumentError
from .services.embeddings import ModelLoadError
from .services.managers import IndexManager, ModelManager, SettingsStore
from .services.pipeline import Services, VerificationError

log = logging.getLogger("truthlens")


def build_services(paths: Paths, models: ModelManager | None = None) -> Services:
    paths.ensure()
    db = Database(paths.db)
    settings = SettingsStore(db)
    models = models or ModelManager(settings)
    index = IndexManager(db, models, settings)
    return Services(paths=paths, db=db, settings=settings, models=models, index=index)


def create_app(paths: Paths | None = None, models: ModelManager | None = None, load_models: bool | None = None) -> FastAPI:
    configure_logging()
    paths = paths or Paths.default()
    configure_hf_cache(paths)
    svc = build_services(paths, models)
    svc.models.on_ready.append(svc.index.rebuild_safe)   # index follows model (re)loads
    if load_models is None:
        load_models = os.environ.get("TRUTHLENS_SKIP_MODEL_LOAD", "0") != "1"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc.db.fail_stale_sessions()
        svc.db.fail_stale_eval_runs()
        if load_models:
            svc.models.start_background()           # models load ONCE here, not per request
        yield
        svc.verify_pool.shutdown(wait=False, cancel_futures=True)
        svc.eval_pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title=f"{APP_NAME} API", version=APP_VERSION, lifespan=lifespan,
        description="Evidence-grounded verification of AI-generated answers: hybrid retrieval + NLI + abstention.")
    app.state.services = svc
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000",
                                       "http://127.0.0.1:8000"],
        allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

    @app.exception_handler(DocumentError)
    async def _doc_err(_: Request, e: DocumentError):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(VerificationError)
    async def _ver_err(_: Request, e: VerificationError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(ModelLoadError)
    async def _model_err(_: Request, e: ModelLoadError):
        return JSONResponse({"detail": str(e), "code": "model_unavailable"}, status_code=503)

    @app.exception_handler(ValidationError)
    async def _pyd_err(_: Request, e: ValidationError):
        msgs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return JSONResponse({"detail": f"Invalid value: {msgs}"}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _req_err(_: Request, e: RequestValidationError):
        msgs = "; ".join(f"{'.'.join(str(p) for p in x['loc'] if p != 'body')}: {x['msg']}" for x in e.errors())
        return JSONResponse({"detail": msgs or "Invalid request"}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("Unhandled error")
        return JSONResponse({"detail": "Internal server error. See the server log for details."}, status_code=500)

    from .api import documents, evaluation, system, verification
    for r in (system.router, documents.router, verification.router, evaluation.router):
        app.include_router(r)

    # Serve the built frontend (production mode: one port) when it exists
    dist = paths.frontend_dist
    if dist.exists() and (dist / "index.html").exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    return app


def get_app() -> FastAPI:
    """Factory used by uvicorn:  uvicorn app.main:get_app --factory"""
    return create_app()
