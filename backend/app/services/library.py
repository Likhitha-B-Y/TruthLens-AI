"""Evidence-library operations shared by the upload endpoint and the sample loader."""
from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from pathlib import Path

from ..config import ALLOWED_EXTENSIONS
from .document_processing import DocumentError, extract_document, safe_filename
from .pipeline import Services

log = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ingest_file(svc: Services, src: Path, display_name: str, *, is_sample: bool = False) -> tuple[dict, bool]:
    """Extract, store and chunk one file. Returns (document_row, created)."""
    name = safe_filename(display_name)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(f"Unsupported file type '{ext or 'unknown'}'. Upload PDF, DOCX or TXT.")
    size = src.stat().st_size
    if size == 0:
        raise DocumentError("The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise DocumentError(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    digest = sha256_file(src)
    existing = svc.db.get_document_by_hash(digest)
    if existing:
        return existing, False

    extracted = extract_document(src, display_name=name)       # raises DocumentError on bad content
    stored = svc.paths.uploads / f"{digest[:12]}_{name}"
    svc.paths.uploads.mkdir(parents=True, exist_ok=True)
    if src.resolve() != stored.resolve():
        shutil.copyfile(src, stored)
    doc_id = svc.db.add_document(
        name=name, ext=ext, size_bytes=size, sha256=digest, stored_path=str(stored),
        pages=extracted.pages, meta=extracted.meta, is_sample=is_sample)
    n = svc.index.chunk_document(doc_id)
    svc.index.mark_dirty()
    log.info("Ingested %s (%d pages, %d passages)", name, len(extracted.pages), n)
    return svc.db.get_document(doc_id), True          # type: ignore[return-value]


def remove_document(svc: Services, doc_id: int) -> bool:
    stored = svc.db.delete_document(doc_id)
    if stored is None:
        return False
    try:
        Path(stored).unlink(missing_ok=True)
    except OSError:
        log.warning("Could not delete stored file %s", stored)
    svc.db.prune_embeddings()
    svc.index.mark_dirty()
    return True


def rebuild_index_async(svc: Services) -> None:
    """Rebuild the index in the background so the HTTP response returns immediately."""
    def _run() -> None:
        try:
            svc.index.rebuild()
        except Exception as e:                                   # model still loading etc.
            log.warning("Background index rebuild skipped: %s", e)
            svc.index.info = {**svc.index.info, "state": "error", "message": str(e)}

    svc.index.info = {**svc.index.info, "state": "building", "message": "Rebuilding indexes..."}
    threading.Thread(target=_run, name="index-rebuild", daemon=True).start()
