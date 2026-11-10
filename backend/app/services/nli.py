"""Natural Language Inference with a pretrained DeBERTa MNLI-style cross-encoder.

Premise = retrieved evidence, hypothesis = extracted claim. The model outputs probabilities for
entailment / contradiction / neutral. Label order is read from the model config, never assumed.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .embeddings import ModelLoadError, resolve_device

log = logging.getLogger(__name__)


@dataclass
class NLIScores:
    entailment: float
    contradiction: float
    neutral: float

    def to_dict(self) -> dict:
        return {"entailment": round(self.entailment, 4), "contradiction": round(self.contradiction, 4),
                "neutral": round(self.neutral, 4)}

    @property
    def argmax(self) -> str:
        return max(("entailment", "contradiction", "neutral"), key=lambda k: getattr(self, k))


class NLIBackend(Protocol):
    model_name: str
    device: str

    def load(self) -> None: ...
    def predict(self, premises: Sequence[str], hypotheses: Sequence[str],
                progress: Callable[[int, int], None] | None = None) -> list[NLIScores]: ...


class DebertaNLI:
    """Hugging Face sequence-classification NLI model (CPU or GPU)."""

    def __init__(self, model_name: str, device: str = "auto", batch_size: int = 8, max_length: int = 512):
        self.model_name = model_name
        self.device = resolve_device(device)
        self.batch_size = batch_size
        self.max_length = max_length
        self._tok = None
        self._model = None
        self._idx: dict[str, int] = {}

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:
            raise ModelLoadError(
                "PyTorch / transformers are not installed. Run: pip install -r backend/requirements.txt"
            ) from e
        try:
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        except Exception as e:
            raise ModelLoadError(
                f"Could not load NLI model '{self.model_name}': {e}. "
                "Check your internet connection for the first download, or run "
                "`python backend/scripts/download_models.py`."
            ) from e
        self._model.to(self.device).eval()
        self._idx = self._label_indices(self._model.config.id2label)
        log.info("Loaded NLI model %s on %s (labels=%s)", self.model_name, self.device, self._idx)

    @staticmethod
    def _label_indices(id2label: dict) -> dict[str, int]:
        idx: dict[str, int] = {}
        for i, lab in id2label.items():
            l = str(lab).lower()
            if "entail" in l:
                idx["entailment"] = int(i)
            elif "contradict" in l:
                idx["contradiction"] = int(i)
            elif "neutral" in l:
                idx["neutral"] = int(i)
        if set(idx) != {"entailment", "contradiction", "neutral"}:
            raise ModelLoadError(
                f"Model labels {dict(id2label)} are not entailment/neutral/contradiction; choose an NLI model."
            )
        return idx

    def predict(self, premises: Sequence[str], hypotheses: Sequence[str],
                progress: Callable[[int, int], None] | None = None) -> list[NLIScores]:
        if self._model is None:
            self.load()
        import torch

        assert len(premises) == len(hypotheses)
        n = len(premises)
        results: list[NLIScores | None] = [None] * n
        order = sorted(range(n), key=lambda i: len(premises[i]) + len(hypotheses[i]))   # less padding
        done = 0
        with torch.inference_mode():
            for s in range(0, n, self.batch_size):
                batch_ids = order[s:s + self.batch_size]
                enc = self._tok(  # type: ignore[misc]
                    [premises[i] for i in batch_ids], [hypotheses[i] for i in batch_ids],
                    truncation="longest_first", max_length=self.max_length, padding=True, return_tensors="pt",
                ).to(self.device)
                logits = self._model(**enc).logits  # type: ignore[misc]
                probs = torch.softmax(logits.float(), dim=-1).cpu().tolist()
                for i, p in zip(batch_ids, probs):
                    results[i] = NLIScores(p[self._idx["entailment"]], p[self._idx["contradiction"]],
                                           p[self._idx["neutral"]])
                done += len(batch_ids)
                if progress:
                    progress(done, n)
        return results  # type: ignore[return-value]


def timed_predict(backend: NLIBackend, premises: Sequence[str], hypotheses: Sequence[str]) -> tuple[list[NLIScores], float]:
    t = time.perf_counter()
    out = backend.predict(premises, hypotheses)
    return out, time.perf_counter() - t
