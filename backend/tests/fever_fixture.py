"""Synthetic data in the exact FEVER file formats, used ONLY to test the evaluation code paths.
Metrics computed on it mean nothing about the real system."""
import json
import random
from pathlib import Path


def make_fever(tmp: Path, n_entities: int = 20, n_distractors: int = 30, seed: int = 1):
    rng = random.Random(seed)
    base = ["Zor", "Bel", "Kin", "Mar", "Tul", "Vex", "Qua", "Dro", "Syl", "Han"]
    suffix = ["vath", "dria", "mont", "gard", "lune", "wick", "stad", "pora", "bury", "ness"]
    names = [f"{a}{b}" for a in base for b in suffix]
    rng.shuffle(names)
    wiki_dir = tmp / "wiki-pages"
    wiki_dir.mkdir()
    pages, claims = [], []
    cid = 1
    for k in range(n_entities):
        name = names[k]
        year, pop = 1500 + 7 * k, 10000 + 313 * k
        sents = [f"{name} is a town in the valley of {names[-1 - k]}.",
                 f"{name} was founded in {year} by traders.",
                 f"The population of {name} is {pop} people.",
                 f"{name} is known for its glass workshops.",
                 f"The river {names[-1 - k]} flows beside {name}."]
        lines = "\n".join(f"{i}\t{s}\t" for i, s in enumerate(sents))
        pid = name
        pages.append({"id": pid, "text": " ".join(sents), "lines": lines})
        ev = lambda i: [[[cid, cid, pid, i]]]  # noqa: E731
        claims.append({"id": cid, "claim": f"{name} was founded in {year}.", "label": "SUPPORTS", "evidence": ev(1)}); cid += 1
        claims.append({"id": cid, "claim": f"{name} was founded in {year + 111}.", "label": "REFUTES", "evidence": ev(1)}); cid += 1
        claims.append({"id": cid, "claim": f"{name} has a famous zoo with pandas.", "label": "NOT ENOUGH INFO",
                       "evidence": [[[cid, None, None, None]]]}); cid += 1
    for k in range(n_distractors):
        sents = [f"Distractor{k} is a lake in a distant land.", f"Distractor{k} freezes every winter."]
        pages.append({"id": f"Distractor{k}", "text": " ".join(sents), "lines": "\n".join(f"{i}\t{s}\t" for i, s in enumerate(sents))})
    half = len(pages) // 2
    for fi, chunk in enumerate((pages[:half], pages[half:]), start=1):
        with open(wiki_dir / f"wiki-{fi:03d}.jsonl", "w", encoding="utf-8") as f:
            for p in chunk:
                f.write(json.dumps(p) + "\n")
    claims_file = tmp / "shared_task_dev.jsonl"
    with open(claims_file, "w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
    return claims_file, wiki_dir
