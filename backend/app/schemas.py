"""Request models for the REST API (responses are plain dicts built from stored JSON)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_ANSWER_CHARS = 30_000


class ClaimInput(BaseModel):
    id: str | None = Field(None, max_length=40)
    text: str = Field(..., min_length=1, max_length=1500)
    sentence: str | None = Field(None, max_length=3000)
    sentence_id: int | None = None
    source: str | None = Field(None, max_length=20)
    resolved_pronoun: bool | None = None
    context_note: str | None = Field(None, max_length=300)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Claim text cannot be empty")
        return v


class ExtractRequest(BaseModel):
    answer: str = Field(..., max_length=MAX_ANSWER_CHARS)
    split_compound: bool | None = None
    resolve_pronouns: bool | None = None
    max_claims: int | None = Field(None, ge=1, le=200)

    @field_validator("answer")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("The answer is empty. Paste the AI-generated answer you want to verify.")
        return v


class VerifyRequest(BaseModel):
    answer: str = Field(..., max_length=MAX_ANSWER_CHARS)
    claims: list[ClaimInput] | None = Field(None, max_length=200)
    document_ids: list[int] | None = Field(None, max_length=500)
    wait: bool = False

    @field_validator("answer")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("The answer is empty. Paste the AI-generated answer you want to verify.")
        return v


class EvalRunRequest(BaseModel):
    fever_path: str | None = Field(None, description="Path to a FEVER jsonl file (shared_task_dev.jsonl)")
    wiki_dir: str | None = Field(None, description="Path to the FEVER wiki-pages directory")
    sample_size: int = Field(150, ge=9, le=3000)
    top_k: int = Field(5, ge=1, le=20)
    window: int = Field(3, ge=1, le=8)
    distractors: int = Field(300, ge=0, le=20000)
    calibration_fraction: float = Field(0.2, ge=0.0, le=0.5)
    seed: int = 13
