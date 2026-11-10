"""Test doubles. These replace ONLY the heavy neural NLI model so the surrounding logic can be tested offline.
The real DeBERTa path is covered by test_real_models.py (opt-in: RUN_MODEL_TESTS=1)."""
from __future__ import annotations

import re

from app.services.nli import NLIScores
from app.services.text_utils import content_words

_NUM = re.compile(r"\d+")


class StubNLI:
    """Rule-based stand-in: high claim coverage -> entailment; same words but different numbers or a
    negation mismatch -> contradiction; otherwise neutral. Deterministic, no download."""

    model_name = "stub-nli (tests only)"
    device = "cpu"

    def load(self) -> None:
        return None

    def predict(self, premises, hypotheses, progress=None):
        out = []
        for i, (p, h) in enumerate(zip(premises, hypotheses), start=1):
            cw, pw = content_words(h), content_words(p)
            cov = len(cw & pw) / len(cw) if cw else 0.0
            nums_h, nums_p = set(_NUM.findall(h)), set(_NUM.findall(p))
            neg_h = bool(re.search(r"\b(not|never|no)\b|n't", h, re.I))
            neg_p = bool(re.search(r"\b(not|never|no)\b|n't", p, re.I))
            if cov >= 0.5 and nums_h and not nums_h <= nums_p:
                s = NLIScores(0.03, 0.94, 0.03)
            elif cov >= 0.6 and neg_h != neg_p:
                s = NLIScores(0.04, 0.92, 0.04)
            elif cov >= 0.75:
                s = NLIScores(0.93, 0.02, 0.05)
            elif cov >= 0.5:
                s = NLIScores(0.45, 0.10, 0.45)
            else:
                s = NLIScores(0.04, 0.03, 0.93)
            out.append(s)
            if progress:
                progress(i, len(premises))
        return out
