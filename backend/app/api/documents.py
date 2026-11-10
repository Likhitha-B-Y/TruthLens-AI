"""Evidence library endpoints."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..services.document_processing import DocumentError, safe_filename
from ..services.library import MAX_UPLOAD_BYTES, ingest_file, rebuild_index_async, remove_document
from ..services.pipeline import Services
from .deps import get_services

router = APIRouter(prefix="/api", tags=["documents"])


def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("stored_path", "sha256")} | {"sha256": d["sha256"][:12]}


@router.post("/documents", status_code=201)
async def upload_documents(files: list[UploadFile] = File(...), svc: Services = Depends(get_services)):
    """Upload one or more PDF / DOCX / TXT files. Each file succeeds or fails independently."""
    if not files:
        raise HTTPException(422, "No files were uploaded.")
    results, created_any = [], False
    for f in files:
        name = safe_filename(f.filename or "document")
        try:
            suffix = Path(name).suffix.lower()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / name
                size = 0
                with open(path, "wb") as out:
                    while chunk := await f.read(1 << 20):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise DocumentError(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
                        out.write(chunk)
                doc, created = ingest_file(svc, path, name)
            created_any = created_any or created
            results.append({"filename": name, "ok": True, "duplicate": not created, "document": _public(doc)})
        except DocumentError as e:
            results.append({"filename": name, "ok": False, "error": str(e), "suffix": suffix})
        finally:
            await f.close()
    if created_any:
        rebuild_index_async(svc)
    return {"results": results, "uploaded": sum(1 for r in results if r["ok"] and not r.get("duplicate")),
            "failed": sum(1 for r in results if not r["ok"])}


@router.get("/documents")
def list_documents(q: str | None = Query(None, max_length=200), ext: str | None = Query(None, max_length=10),
                   svc: Services = Depends(get_services)):
    docs = svc.db.list_documents()
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in d["name"].lower() or ql in (d["meta"].get("title") or "").lower()
                or ql in (d["meta"].get("author") or "").lower()]
    if ext:
        e = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        docs = [d for d in docs if d["ext"] == e]
    return {"documents": [_public(d) for d in docs], "total": len(docs), "index": svc.index.info}


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, svc: Services = Depends(get_services)):
    d = svc.db.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Document not found.")
    return {**_public(d), "passages": svc.db.get_passages_for_doc(doc_id, limit=12)}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, svc: Services = Depends(get_services)):
    if not remove_document(svc, doc_id):
        raise HTTPException(404, "Document not found.")
    rebuild_index_async(svc)
    return {"deleted": doc_id}


@router.post("/documents/rebuild-index")
def rebuild_index(wait: bool = False, svc: Services = Depends(get_services)):
    svc.index.mark_dirty()
    if wait:
        return svc.index.rebuild()
    rebuild_index_async(svc)
    return svc.index.info


@router.get("/index/status")
def index_status(svc: Services = Depends(get_services)):
    return svc.index.info
