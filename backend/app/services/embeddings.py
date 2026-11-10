"""Dense embedding backends.

* `SentenceTransformerEmbedder` - the real semantic model (default: all-MiniLM-L6-v2).
* `TfidfLsaEmbedder` - a corpus-fitted TF-IDF + truncated-SVD (LSA) fallback that needs no download.
  It is used automatically (embedding_backend="auto") when the transformer model cannot be loaded,
  and the UI/model-status endpoint says so. It is weaker than a transformer model.
"""
from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class ModelLoadError(RuntimeError):
    """A model could not be loaded (download failure, missing library, out of memory ...)."""


class Embedder(Protocol):
    name: str
    needs_fit: bool
    cacheable: bool

    def fit(self, texts: list[str]) -> None: ...
    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray: ...


def _l2norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


def resolve_device(pref: str) -> str:
    if pref in ("cpu", "cuda"):
        if pref == "cuda":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        return "cpu"
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class SentenceTransformerEmbedder:
    needs_fit = False
    cacheable = True

    def __init__(self, model_name: str, device: str = "auto"):
        self.name = model_name
        self.device = resolve_device(device)
        self._model = None

    def load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ModelLoadError(
                "sentence-transformers is not installed. Run: pip install -r backend/requirements.txt"
            ) from e
        try:
            self._model = SentenceTransformer(self.name, device=self.device)
        except Exception as e:  # network errors, bad model id, OOM ...
            raise ModelLoadError(f"Could not load embedding model '{self.name}': {e}") from e
        log.info("Loaded embedding model %s on %s", self.name, self.device)

    def fit(self, texts: list[str]) -> None:  # not needed
        return None

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if self._model is None:
            self.load()
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        vecs = self._model.encode(  # type: ignore[union-attr]
            texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(vecs, dtype=np.float32)


class TfidfLsaEmbedder:
    """Corpus-fitted TF-IDF + SVD embedding (classic latent semantic analysis)."""

    needs_fit = True
    cacheable = False

    def __init__(self, n_components: int = 128):
        self.name = "tfidf-lsa"
        self.n_components = n_components
        self._vec = None
        self._svd = None
        self._dim = 1

    def fit(self, texts: list[str]) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        from .text_utils import tokenize

        self._vec = TfidfVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None,
                                    sublinear_tf=True, ngram_range=(1, 2), min_df=1)
        X = self._vec.fit_transform(texts)
        max_comp = min(self.n_components, X.shape[0] - 1, X.shape[1] - 1)
        if max_comp >= 2:
            self._svd = TruncatedSVD(n_components=max_comp, random_state=0)
            self._svd.fit(X)
            self._dim = max_comp
        else:  # tiny corpus: plain TF-IDF vectors
            self._svd = None
            self._dim = X.shape[1]

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if self._vec is None:
            raise ModelLoadError("TF-IDF/LSA embedder must be fitted on the corpus before encoding.")
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        X = self._vec.transform(texts)
        dense = self._svd.transform(X) if self._svd is not None else X.toarray()
        return _l2norm(np.asarray(dense, dtype=np.float32))
