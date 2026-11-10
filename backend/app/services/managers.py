"""Long-lived singletons: settings store, model manager (load once at startup), index manager."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from ..config import RuntimeSettings
from ..database import Database
from .document_processing import chunk_pages
from .embeddings import Embedder, ModelLoadError, SentenceTransformerEmbedder, TfidfLsaEmbedder
from .nli import DebertaNLI, NLIBackend
from .retrieval import HybridRetriever, PassageRecord

log = logging.getLogger(__name__)


# ======================================================================= settings
class SettingsStore:
    KEY = "runtime_settings"

    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.Lock()

    def get(self) -> RuntimeSettings:
        raw = self.db.get_setting(self.KEY, {})
        try:
            return RuntimeSettings(**raw)
        except Exception:
            log.warning("Stored settings invalid; falling back to defaults")
            return RuntimeSettings()

    def update(self, patch: dict) -> RuntimeSettings:
        with self._lock:
            merged = {**self.get().model_dump(), **{k: v for k, v in patch.items() if v is not None}}
            new = RuntimeSettings(**merged)          # raises ValidationError on bad values
            self.db.set_setting(self.KEY, new.model_dump())
            return new

    def reset(self) -> RuntimeSettings:
        self.db.delete_setting(self.KEY)
        return RuntimeSettings()


# ================================================================ model manager
def _blank(kind: str) -> dict:
    return {"kind": kind, "state": "not_loaded", "model": None, "device": None, "message": "",
            "load_seconds": None, "backend": None}


class ModelManager:
    """Loads the embedding model and NLI model once and shares them across requests."""

    def __init__(self, settings: SettingsStore, nli_factory: Callable[[RuntimeSettings], NLIBackend] | None = None,
                 embedder_factory: Callable[[RuntimeSettings], Embedder] | None = None):
        self.settings = settings
        self._nli_factory = nli_factory or (lambda s: DebertaNLI(s.nli_model, s.device, s.nli_batch_size))
        self._emb_factory = embedder_factory or (lambda s: SentenceTransformerEmbedder(s.embedding_model, s.device))
        self.nli: NLIBackend | None = None
        self.embedder: Embedder | None = None
        self.status = {"nli": _blank("nli"), "embedding": _blank("embedding")}
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.generation = 0                    # bumps whenever the embedder changes (index must rebuild)
        self.on_ready: list[Callable[[], None]] = []   # called after every (re)load, e.g. to rebuild the index

    # ------------------------------------------------------------------ loading
    def start_background(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._ready.clear()
            self._thread = threading.Thread(target=self.load_all, name="model-loader", daemon=True)
            self._thread.start()

    def load_all(self) -> None:
        s = self.settings.get()
        with self._lock:
            self._ready.clear()
            self.nli, self.embedder = None, None
            self.status["nli"] = {**_blank("nli"), "state": "loading", "model": s.nli_model,
                                  "message": "Loading NLI model (first run downloads weights)..."}
            self.status["embedding"] = {**_blank("embedding"), "state": "loading", "model": s.embedding_model,
                                        "message": "Loading embedding model..."}
        self._load_embedder(s)
        self._load_nli(s)
        with self._lock:
            self.generation += 1
        self._ready.set()
        for cb in list(self.on_ready):
            try:
                cb()
            except Exception:  # a failing callback must never break model loading
                log.exception("on_ready callback failed")

    def _load_embedder(self, s: RuntimeSettings) -> None:
        t = time.perf_counter()
        st = self.status["embedding"]
        if s.embedding_backend == "tfidf-lsa":
            self.embedder = TfidfLsaEmbedder()
            st.update(state="ready", backend="tfidf-lsa", model="tfidf-lsa", message="Using TF-IDF + LSA (no download).",
                      load_seconds=0.0)
            return
        try:
            emb = self._emb_factory(s)
            if hasattr(emb, "load"):
                emb.load()  # type: ignore[attr-defined]
            self.embedder = emb
            st.update(state="ready", backend="tfidf-lsa" if emb.needs_fit else "sentence-transformers",
                      model=getattr(emb, "name", s.embedding_model), device=getattr(emb, "device", None),
                      message="Ready.", load_seconds=round(time.perf_counter() - t, 2))
        except ModelLoadError as e:
            log.error("Embedding model failed: %s", e)
            if s.embedding_backend == "auto":
                self.embedder = TfidfLsaEmbedder()
                st.update(state="fallback", backend="tfidf-lsa", model="tfidf-lsa",
                          message=f"{e} Falling back to TF-IDF + LSA dense retrieval (weaker). "
                                  "Fix the download and click 'Reload models'.")
            else:
                st.update(state="error", message=str(e))

    def _load_nli(self, s: RuntimeSettings) -> None:
        t = time.perf_counter()
        st = self.status["nli"]
        try:
            nli = self._nli_factory(s)
            nli.load()
            self.nli = nli
            st.update(state="ready", device=nli.device, message="Ready.", model=getattr(nli, "model_name", s.nli_model),
                      load_seconds=round(time.perf_counter() - t, 2), backend="transformers")
        except ModelLoadError as e:
            log.error("NLI model failed: %s", e)
            st.update(state="error", message=str(e))
        except Exception as e:  # pragma: no cover - unexpected
            log.exception("NLI model failed unexpectedly")
            st.update(state="error", message=f"Unexpected error loading NLI model: {e}")

    # ----------------------------------------------------------------- access
    def wait_ready(self, timeout: float = 0.0) -> bool:
        return self._ready.wait(timeout) if timeout else self._ready.is_set()

    def require_nli(self) -> NLIBackend:
        if self.nli is None:
            st = self.status["nli"]
            if st["state"] == "loading":
                raise ModelLoadError("The NLI model is still loading. Try again in a moment.")
            raise ModelLoadError(st["message"] or "NLI model is not loaded.")
        return self.nli

    def require_embedder(self) -> Embedder:
        if self.embedder is None:
            st = self.status["embedding"]
            raise ModelLoadError(st["message"] or "Embedding model is not loaded.")
        return self.embedder

    def snapshot(self) -> dict:
        with self._lock:
            return {"ready": self._ready.is_set(), "nli": dict(self.status["nli"]),
                    "embedding": dict(self.status["embedding"])}


# ================================================================ index manager
class IndexManager:
    """Owns the corpus-wide BM25 + FAISS index and rebuilds it when documents or settings change."""

    def __init__(self, db: Database, models: ModelManager, settings: SettingsStore):
        self.db, self.models, self.settings = db, models, settings
        self._lock = threading.RLock()
        self._retriever: HybridRetriever | None = None
        self._dirty = True
        self._built_for = ""
        self._built_generation = -1
        self.info = {"state": "empty", "passages": 0, "documents": 0, "built_at": None,
                     "build_seconds": None, "embedding_backend": None, "message": ""}

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True

    def rebuild_safe(self) -> None:
        """Rebuild without raising (used from background callbacks); records failures in `info`."""
        try:
            self.rebuild()
        except Exception as e:
            log.warning("Index rebuild failed: %s", e)
            self.info = {**self.info, "state": "error", "message": str(e)}

    # ---------------------------------------------------------- chunking
    def chunk_document(self, doc_id: int, s: RuntimeSettings | None = None) -> int:
        s = s or self.settings.get()
        pages = self.db.get_pages(doc_id)
        drafts = chunk_pages(pages, s.chunk_words, s.chunk_overlap_sentences)
        self.db.replace_passages(doc_id, [d.__dict__ for d in drafts])
        return len(drafts)

    def _rechunk_if_needed(self, s: RuntimeSettings) -> None:
        sig = s.chunk_signature()
        if self.db.get_setting("chunk_signature") == sig:
            return
        for d in self.db.list_documents():
            self.chunk_document(d["id"], s)
        self.db.set_setting("chunk_signature", sig)
        self.db.prune_embeddings()

    # ------------------------------------------------------------- build
    def rebuild(self, force: bool = True) -> dict:
        with self._lock:
            s = self.settings.get()
            t0 = time.perf_counter()
            self._rechunk_if_needed(s)
            rows = self.db.all_passages()
            docs = {r["doc_id"] for r in rows}
            if not rows:
                self._retriever = None
                self._dirty = False
                self.info = {**self.info, "state": "empty", "passages": 0, "documents": 0,
                             "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "message": "No documents indexed yet."}
                return self.info
            embedder = self.models.require_embedder()
            passages = [PassageRecord(r["id"], r["doc_id"], r["doc_name"], r["page"], r["idx"], r["text"], r["text_hash"])
                        for r in rows]
            texts = [p.text for p in passages]
            if embedder.needs_fit:
                embedder.fit(texts)
                matrix = embedder.encode(texts)
            else:
                matrix = self._cached_embeddings(embedder, passages)
            self._retriever = HybridRetriever(passages, matrix, embedder)
            self._dirty = False
            self._built_generation = self.models.generation
            self.info = {
                "state": "ready", "passages": len(passages), "documents": len(docs),
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "build_seconds": round(time.perf_counter() - t0, 2),
                "embedding_backend": self.models.status["embedding"].get("backend"),
                "message": "BM25 and dense indexes are up to date.",
            }
            log.info("Index rebuilt: %d passages from %d documents in %.2fs", len(passages), len(docs),
                     time.perf_counter() - t0)
            return self.info

    def _cached_embeddings(self, embedder: Embedder, passages: list[PassageRecord]) -> np.ndarray:
        cached = self.db.get_embeddings([p.text_hash for p in passages], embedder.name)
        missing = [p for p in passages if p.text_hash not in cached]
        if missing:
            uniq: dict[str, str] = {p.text_hash: p.text for p in missing}
            vecs = embedder.encode(list(uniq.values()))
            new = {h: v for h, v in zip(uniq.keys(), vecs)}
            self.db.put_embeddings(new, embedder.name)
            cached.update(new)
            log.info("Embedded %d new passages (%d cached)", len(uniq), len(passages) - len(missing))
        return np.vstack([cached[p.text_hash] for p in passages])

    def get_retriever(self) -> HybridRetriever | None:
        with self._lock:
            if self._dirty or self._built_generation != self.models.generation:
                self.rebuild()
            return self._retriever
