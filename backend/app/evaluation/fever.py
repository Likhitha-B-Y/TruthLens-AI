"""FEVER data loading: claims, Wikipedia pages and sentence-window passages.

FEVER full-Wikipedia retrieval is too heavy for a student laptop, so evaluation runs on a *closed subset corpus*:
the Wikipedia pages holding the gold evidence of the sampled claims plus randomly sampled distractor pages.
Metrics are therefore relative to this subset and are NOT comparable with FEVER leaderboard numbers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import STATUS_CONTRADICTED, STATUS_INSUFFICIENT, STATUS_SUPPORTED
from ..services.retrieval import PassageRecord

log = logging.getLogger(__name__)

LABEL_MAP = {"SUPPORTS": STATUS_SUPPORTED, "REFUTES": STATUS_CONTRADICTED, "NOT ENOUGH INFO": STATUS_INSUFFICIENT}
CLAIM_FILE_PREFERENCE = ("paper_dev.jsonl", "shared_task_dev.jsonl", "dev.jsonl")


class FeverDataError(Exception):
    pass


@dataclass
class FeverClaim:
    id: int
    claim: str
    label: str                                              # SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE
    gold_groups: list[list[tuple[str, int]]] = field(default_factory=list)   # [[(page, sent_id), ...], ...]

    @property
    def verifiable(self) -> bool:
        return self.label != STATUS_INSUFFICIENT and bool(self.gold_groups)


# ------------------------------------------------------------------ discovery
def discover_fever_files(eval_dir: Path) -> dict:
    base = Path(eval_dir) / "data" / "fever"
    claims_file = next((str(base / n) for n in CLAIM_FILE_PREFERENCE if (base / n).exists()), None)
    wiki_dir = None
    for cand in (base / "wiki-pages", base / "wiki-pages" / "wiki-pages"):
        if cand.is_dir() and any(cand.glob("*.jsonl")):
            wiki_dir = str(cand)
            break
    return {"claims_file": claims_file, "wiki_dir": wiki_dir, "data_dir": str(base),
            "ready": bool(claims_file and wiki_dir)}


# --------------------------------------------------------------------- claims
def _parse_claim(obj: dict) -> FeverClaim | None:
    label = LABEL_MAP.get(obj.get("label", ""))
    if label is None or not obj.get("claim"):
        return None
    groups: list[list[tuple[str, int]]] = []
    for grp in obj.get("evidence") or []:
        g = [(ev[2], int(ev[3])) for ev in grp if len(ev) >= 4 and ev[2] is not None and ev[3] is not None]
        if g:
            groups.append(g)
    if label != STATUS_INSUFFICIENT and not groups:
        return None
    return FeverClaim(int(obj.get("id", 0)), obj["claim"].strip(), label, groups if label != STATUS_INSUFFICIENT else [])


def load_claims(path: str | Path, sample_size: int, seed: int = 13) -> list[FeverClaim]:
    """Stratified (balanced) random sample: sample_size/3 claims per label."""
    path = Path(path)
    if not path.exists():
        raise FeverDataError(f"FEVER claims file not found: {path}")
    by_label: dict[str, list[FeverClaim]] = {STATUS_SUPPORTED: [], STATUS_CONTRADICTED: [], STATUS_INSUFFICIENT: []}
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = _parse_claim(json.loads(line))
            if c and c.claim not in seen:
                seen.add(c.claim)
                by_label[c.label].append(c)
    per = max(1, sample_size // 3)
    rng = random.Random(seed)
    out: list[FeverClaim] = []
    for label, items in by_label.items():
        if len(items) < per:
            raise FeverDataError(f"Only {len(items)} usable '{label}' claims in {path.name}; need {per}.")
        rng.shuffle(items)
        out.extend(items[:per])
    rng.shuffle(out)
    return out


# ------------------------------------------------------------------ wikipedia
_DECODE = {"-LRB-": "(", "-RRB-": ")", "-LSB-": "[", "-RSB-": "]", "-LCB-": "{", "-RCB-": "}", "-COLON-": ":"}


def readable_title(page_id: str) -> str:
    t = page_id
    for k, v in _DECODE.items():
        t = t.replace(k, v)
    return t.replace("_", " ")


def parse_lines(lines: str) -> list[tuple[int, str]]:
    out = []
    for row in lines.split("\n"):
        parts = row.split("\t")
        if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip():
            out.append((int(parts[0]), parts[1].strip()))
    return out


def _quick_id(line: str) -> str | None:
    """Fast extraction of the page id from a wiki-pages jsonl line without parsing the whole JSON."""
    prefix = '{"id": "'
    if not line.startswith(prefix):
        return None
    end = line.find('", "text":', len(prefix))
    return line[len(prefix):end] if end > 0 else None


def collect_pages(wiki_dir: str | Path, needed: set[str], distractors: int, seed: int,
                  progress: Callable[[int, int], None] | None = None) -> dict[str, list[tuple[int, str]]]:
    files = sorted(Path(wiki_dir).glob("*.jsonl"))
    if not files:
        raise FeverDataError(f"No *.jsonl files found in {wiki_dir}")
    rng = random.Random(seed)
    per_file = max(1, -(-distractors // len(files))) if distractors else 0
    pages: dict[str, list[tuple[int, str]]] = {}
    for fi, fp in enumerate(files):
        reservoir: list[str] = []
        seen = 0
        with open(fp, encoding="utf-8") as f:
            for line in f:
                pid = _quick_id(line)
                if pid is None:
                    try:
                        pid = json.loads(line)["id"]
                    except Exception:
                        continue
                if pid in needed:
                    obj = json.loads(line)
                    sents = parse_lines(obj.get("lines", ""))
                    if sents:
                        pages[pid] = sents
                elif per_file:
                    seen += 1
                    if len(reservoir) < per_file:
                        reservoir.append(line)
                    else:
                        j = rng.randrange(seen)
                        if j < per_file:
                            reservoir[j] = line
        for line in reservoir:
            obj = json.loads(line)
            sents = parse_lines(obj.get("lines", ""))
            if len(sents) >= 2 and obj["id"] not in pages:
                pages[obj["id"]] = sents
        if progress:
            progress(fi + 1, len(files))
    missing = needed - set(pages)
    if missing:
        log.warning("%d gold evidence pages were not found in the wiki dump", len(missing))
    return pages


def build_passages(pages: dict[str, list[tuple[int, str]]], window: int = 3) -> list[PassageRecord]:
    """Sentence-window passages with 1-sentence overlap. Each passage remembers its page and sentence ids."""
    passages: list[PassageRecord] = []
    step = max(1, window - 1)
    for doc_idx, (pid, sents) in enumerate(sorted(pages.items())):
        n = len(sents)
        starts = list(range(0, max(n - window, 0) + 1, step))
        if starts[-1] + window < n:
            starts.append(n - window)
        title = readable_title(pid)
        for k, s in enumerate(starts):
            chunk = sents[s:s + window]
            text = f"{title}: " + " ".join(t for _, t in chunk)
            passages.append(PassageRecord(
                id=len(passages), doc_id=doc_idx, doc_name=title, page=1, idx=k, text=text,
                text_hash=hashlib.md5(text.encode()).hexdigest(),
                meta={"page_id": pid, "sent_ids": [i for i, _ in chunk]}))
    return passages


def corpus_cache_key(claims: list[FeverClaim], distractors: int, seed: int, window: int, wiki_dir: str) -> str:
    h = hashlib.sha1(f"{[c.id for c in claims]}|{distractors}|{seed}|{window}|{wiki_dir}".encode()).hexdigest()
    return h[:16]


def load_or_build_pages(claims: list[FeverClaim], wiki_dir: str, distractors: int, seed: int, window: int,
                        cache_dir: Path, progress=None) -> dict[str, list[tuple[int, str]]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"fever_subset_{corpus_cache_key(claims, distractors, seed, window, wiki_dir)}.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return {k: [(int(a), b) for a, b in v] for k, v in raw.items()}
    needed = {p for c in claims for g in c.gold_groups for p, _ in g}
    pages = collect_pages(wiki_dir, needed, distractors, seed, progress)
    cache.write_text(json.dumps(pages), encoding="utf-8")
    return pages
