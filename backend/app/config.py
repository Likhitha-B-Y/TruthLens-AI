"""Application paths and runtime settings.

`Paths` describes where the app keeps its files. `RuntimeSettings` holds every
user-tunable option (models, retrieval, NLI thresholds); it is persisted in
SQLite and editable from the Settings page.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

APP_NAME = "TruthLens AI"
APP_VERSION = "1.0.0"

STATUS_SUPPORTED = "SUPPORTED"
STATUS_CONTRADICTED = "CONTRADICTED"
STATUS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
STATUSES = (STATUS_SUPPORTED, STATUS_CONTRADICTED, STATUS_INSUFFICIENT)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Models offered in the Settings page. Any Hugging Face NLI sequence-classification
# model with entailment / neutral / contradiction labels can be typed in manually.
NLI_MODEL_CHOICES = [
    {
        "id": "cross-encoder/nli-deberta-v3-base",
        "label": "DeBERTa-v3 base (SNLI + MultiNLI) - recommended",
        "note": "Best accuracy/speed balance on CPU. Not trained on FEVER, so safe to evaluate on FEVER.",
    },
    {
        "id": "cross-encoder/nli-deberta-v3-small",
        "label": "DeBERTa-v3 small (SNLI + MultiNLI)",
        "note": "Faster, lower accuracy. Good for older laptops.",
    },
    {
        "id": "cross-encoder/nli-deberta-v3-xsmall",
        "label": "DeBERTa-v3 xsmall (SNLI + MultiNLI)",
        "note": "Smallest and fastest. Use when memory is tight.",
    },
    {
        "id": "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        "label": "DeBERTa-v3 base (MNLI + FEVER-NLI + ANLI)",
        "note": "Strong, but trained on FEVER-NLI - do NOT use it for the FEVER evaluation (data leakage).",
    },
]
EMBEDDING_MODEL_CHOICES = [
    {"id": "sentence-transformers/all-MiniLM-L6-v2", "label": "all-MiniLM-L6-v2 (fast, 384-d) - recommended"},
    {"id": "BAAI/bge-small-en-v1.5", "label": "bge-small-en-v1.5 (384-d)"},
    {"id": "sentence-transformers/all-mpnet-base-v2", "label": "all-mpnet-base-v2 (768-d, slower)"},
]


@dataclass
class Paths:
    root: Path
    data: Path
    uploads: Path
    models: Path
    samples: Path
    reports: Path
    evaluation: Path
    db: Path
    frontend_dist: Path

    @classmethod
    def default(cls) -> "Paths":
        root = Path(os.environ.get("TRUTHLENS_ROOT", Path(__file__).resolve().parents[2]))
        data = Path(os.environ.get("TRUTHLENS_DATA_DIR", root / "data"))
        return cls.from_dirs(root=root, data=data)

    @classmethod
    def from_dirs(cls, root: Path, data: Path | None = None, reports: Path | None = None) -> "Paths":
        root = Path(root)
        data = Path(data) if data else root / "data"
        return cls(
            root=root,
            data=data,
            uploads=data / "uploads",
            models=data / "models",
            samples=root / "data" / "samples",
            reports=Path(reports) if reports else root / "reports",
            evaluation=root / "evaluation",
            db=data / "truthlens.db",
            frontend_dist=root / "frontend" / "dist",
        )

    def ensure(self) -> None:
        for p in (self.data, self.uploads, self.models, self.reports, self.evaluation / "results", self.evaluation / "cache"):
            p.mkdir(parents=True, exist_ok=True)


def configure_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=getattr(logging, (level or os.environ.get("TRUTHLENS_LOG_LEVEL", "INFO")).upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Keep third-party noise down
    for noisy in ("httpx", "urllib3", "huggingface_hub", "sentence_transformers", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def configure_hf_cache(paths: Paths) -> None:
    """Keep downloaded model weights inside the project's data/models folder."""
    os.environ.setdefault("HF_HOME", str(paths.models))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(paths.models / "sentence-transformers"))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class RuntimeSettings(BaseModel):
    """All user-configurable options. Validated on every update."""

    # --- Models ---------------------------------------------------------
    nli_model: str = "cross-encoder/nli-deberta-v3-base"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # auto: try sentence-transformers, fall back to TF-IDF + LSA if it cannot load
    embedding_backend: Literal["auto", "sentence-transformers", "tfidf-lsa"] = "auto"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    nli_batch_size: int = Field(8, ge=1, le=64)

    # --- Chunking (changing these re-chunks documents on next index rebuild)
    chunk_words: int = Field(120, ge=30, le=300)
    chunk_overlap_sentences: int = Field(1, ge=0, le=3)

    # --- Retrieval ------------------------------------------------------
    top_k: int = Field(5, ge=1, le=20)
    bm25_candidates: int = Field(20, ge=5, le=100)
    dense_candidates: int = Field(20, ge=5, le=100)
    rrf_k: int = Field(60, ge=1, le=200)
    bm25_weight: float = Field(1.0, ge=0.0, le=5.0)
    dense_weight: float = Field(1.0, ge=0.0, le=5.0)

    # --- NLI verification / aggregation ---------------------------------
    nli_top_k: int = Field(5, ge=1, le=20)
    entail_threshold: float = Field(0.70, ge=0.34, le=0.99)
    contradict_threshold: float = Field(0.70, ge=0.34, le=0.99)
    margin: float = Field(0.10, ge=0.0, le=0.5)
    review_threshold: float = Field(0.85, ge=0.34, le=1.0)
    near_miss_floor: float = Field(0.40, ge=0.0, le=0.99)

    # --- Claim extraction -----------------------------------------------
    split_compound: bool = True
    resolve_pronouns: bool = True
    max_claims: int = Field(60, ge=1, le=200)

    # --- UI --------------------------------------------------------------
    theme: Literal["light", "dark", "system"] = "system"

    @model_validator(mode="after")
    def _check(self) -> "RuntimeSettings":
        if self.nli_top_k > self.top_k:
            # NLI can only run on retrieved passages
            self.nli_top_k = self.top_k
        return self

    def model_fields_requiring_reload(self) -> tuple:
        return (self.nli_model, self.embedding_model, self.embedding_backend, self.device)

    def chunk_signature(self) -> str:
        return f"{self.chunk_words}:{self.chunk_overlap_sentences}"
