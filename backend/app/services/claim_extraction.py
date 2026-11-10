"""Claim extraction: sentence splitting -> atomic factual claims.

This is a transparent rule-based extractor (no model download needed). It:
  * splits the answer into sentences and drops questions / chit-chat,
  * strips discourse markers and citation marks,
  * breaks compound statements ("X did A and B", "X is A; Y is B", "X, which is Y")
    into atomic claims, copying the shared subject,
  * lightly resolves leading pronouns ("It was ...") using the previous sentence's subject,
  * keeps the original sentence for context.

Users can review, edit, add and delete claims before verification, because
rule-based decomposition is heuristic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .text_utils import normalize_text, split_sentences, strip_citation_marks

try:  # optional: better sentence segmentation when spaCy + model are installed
    import spacy  # type: ignore

    _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
except Exception:  # pragma: no cover - spaCy is optional
    _NLP = None


AUX = {
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "will", "would", "can", "could",
    "should", "may", "might", "must", "does", "do", "did", "shall",
}
COMMON_VERBS = {
    "founded", "located", "born", "died", "invented", "discovered", "wrote", "written", "built", "won", "led",
    "became", "known", "used", "makes", "made", "contains", "includes", "produces", "causes", "helps",
    "requires", "provides", "supports", "serves", "operates", "employs", "hosts", "covers", "lies", "sits",
    "stands", "runs", "flows", "measures", "weighs", "orbits", "consists", "comprises", "uses", "takes",
    "gives", "holds", "reaches", "remains", "absorbs", "reflects", "converts", "releases", "occurs", "takes",
    "completed", "opened", "designed", "created", "developed", "established", "launched", "published",
    "attracts", "receives", "welcomes", "features", "offers", "needs", "keeps", "sells", "develops",
    "builds", "grows", "lives", "travels", "moves", "emits", "generates", "forms", "starts", "ends",
    "began", "begins", "spans", "crosses", "borders", "contributes", "plays", "works", "stores", "creates",
    "won", "earned", "received", "scored", "joined", "left", "moved", "ruled", "reigned", "served", "lasted",
    "took", "gave", "got", "went", "came", "saw", "said", "called", "named", "set", "rose", "fell",
}
_NOT_VERBS_ED = {"united", "red", "bed", "need", "speed", "seed", "feed", "weed", "hundred", "sacred",
                 "naked", "wicked", "kindred", "indeed", "breed", "creed", "greed", "shed", "bleed"}
_PRONOUNS_START = {"it", "this", "they", "he", "she", "that", "these", "those", "the", "its", "their"}
_DETERMINERS = {"the", "a", "an", "this", "that", "these", "those", "its", "their", "his", "her", "our",
                "my", "your", "some", "many", "most", "all", "each", "every", "no", "several", "both"}

_DISCOURSE = re.compile(
    r"^(?:however|moreover|furthermore|additionally|in addition|also|therefore|thus|hence|consequently|"
    r"in conclusion|to summarize|in summary|overall|finally|first(?:ly)?|second(?:ly)?|third(?:ly)?|"
    r"lastly|notably|importantly|interestingly|meanwhile|in fact|indeed|similarly|likewise|for example|"
    r"for instance|as a result|in particular|specifically)\s*,\s*",
    re.IGNORECASE,
)
_META = re.compile(
    r"^(?:sure|certainly|of course|absolutely|great question|here (?:is|are)|here's|i hope|hope this helps|"
    r"let me know|feel free|as an ai|i'm sorry|i am sorry|thank you|thanks|hello|hi\b|hey\b|let me|i can help|"
    r"i would be happy|i'd be happy|please note|note that|in this answer|below is|below are)",
    re.IGNORECASE,
)
_OPINION_ONLY = re.compile(r"^(?:i (?:think|believe|feel|guess|suppose)|in my opinion|personally)\b", re.IGNORECASE)


@dataclass
class Claim:
    id: str
    text: str
    sentence_id: int
    sentence: str
    order: int
    source: str = "auto"             # auto | user
    resolved_pronoun: bool = False
    context_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------- helpers
def _words(s: str) -> list[str]:
    return s.split()


def _bare(tok: str) -> str:
    return tok.strip(",.;:!?\"'()[]").lower()


def _is_verb(tok: str) -> bool:
    t = _bare(tok)
    if not t:
        return False
    if t in AUX or t in COMMON_VERBS:
        return True
    return len(t) > 4 and t.endswith("ed") and t not in _NOT_VERBS_ED


def _find_verb_index(words: list[str], start: int = 1) -> int | None:
    for i in range(start, len(words)):
        if _is_verb(words[i]):
            return i
    return None


def _capitalize_first(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def _finish(s: str) -> str:
    s = s.strip().strip(",;:").strip()
    if s and s[-1] not in ".!?":
        s += "."
    return _capitalize_first(s)


def _wc(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", s))


def _sentences(text: str) -> list[str]:
    if _NLP is not None:  # pragma: no cover
        try:
            return [s.text.strip() for s in _NLP(text).sents if s.text.strip()]
        except Exception:
            pass
    return split_sentences(text)


# ----------------------------------------------------------- decomposition
_SPLIT_PATTERNS = [
    re.compile(r",\s+(?:and|but|while|whereas|yet)\s+", re.IGNORECASE),
    re.compile(r"\s+(?:and|but)\s+", re.IGNORECASE),
]
_REL_CLAUSE = re.compile(r"^(?P<main>.+?),\s+which\s+(?P<rest>(?:is|was|are|were|has|have|had)\b.+)$", re.IGNORECASE)


def _subject_of(words: list[str]) -> str | None:
    vi = _find_verb_index(words, 1)
    if vi is None or vi == 0:
        return None
    return " ".join(words[:vi])


def _split_coordination(sentence: str) -> list[str] | None:
    """Try to split one coordinated clause into two. Returns None if no safe split."""
    body = sentence.rstrip(".!? ")
    for pat in _SPLIT_PATTERNS:
        for m in pat.finditer(body):
            left, right = body[:m.start()].strip(), body[m.end():].strip()
            lw, rw = _words(left), _words(right)
            if len(lw) < 3 or len(rw) < 2:
                continue
            first = rw[0]
            # Case A: right side is a bare predicate -> reuse the left subject
            if _is_verb(first) and _bare(first) not in {"been", "being"}:
                subj = _subject_of(lw)
                if subj:
                    return [_finish(left), _finish(f"{subj} {right}")]
            # Case B: right side is an independent clause (has its own subject + auxiliary/verb early on)
            head = rw[:6]
            if len(rw) >= 3 and any(_bare(w) in AUX or _is_verb(w) for w in head[1:]):
                if first[:1].isupper() or _bare(first) in _DETERMINERS or _bare(first) in {"it", "they", "he", "she"}:
                    return [_finish(left), _finish(right)]
    return None


def decompose(sentence: str, depth: int = 0) -> list[str]:
    """Break a sentence into atomic claims (best effort)."""
    body = sentence.strip()
    if not body or depth > 3:
        return [_finish(body)] if body else []

    # 1) semicolons separate independent statements
    if ";" in body:
        parts = [p.strip() for p in body.rstrip(".!? ").split(";") if p.strip()]
        if len(parts) > 1 and all(_wc(p) >= 3 for p in parts):
            out: list[str] = []
            for p in parts:
                out.extend(decompose(p, depth + 1))
            return out

    # 2) trailing ", which is ..." relative clause
    m = _REL_CLAUSE.match(body.rstrip(".!? "))
    if m:
        main, rest = m.group("main"), m.group("rest")
        subj_words = _words(main)
        vi = _find_verb_index(subj_words, 1)
        subj = " ".join(subj_words[:vi]) if vi else main
        # relative clause is attributed to the main subject (users can edit if it modifies the object)
        target = subj if vi else main
        parts = [main, f"{target} {rest}"]
        if all(_wc(p) >= 3 for p in parts):
            out = []
            for p in parts:
                out.extend(decompose(p, depth + 1))
            return out

    # 3) coordination: "X did A and B"
    split = _split_coordination(body)
    if split and all(_wc(p) >= 3 for p in split):
        out = []
        for p in split:
            out.extend(decompose(p, depth + 1))
        return out

    return [_finish(body)]


# --------------------------------------------------------------- public API
def _subject_phrase(sentence: str) -> str | None:
    """Subject noun phrase of a sentence (text before the first verb), if it looks like a named thing."""
    words = _words(sentence)
    vi = _find_verb_index(words, 1)
    if vi is None or vi > 7:
        return None
    subj = " ".join(words[:vi]).strip(",")
    if _bare(words[0]) in {"it", "this", "they", "he", "she", "that", "these", "those", "there", "its"}:
        return None
    return subj


def _resolve_pronoun(claim: str, prev_subject: str | None) -> tuple[str, bool]:
    if not prev_subject:
        return claim, False
    m = re.match(r"^(It|This|They|He|She)\s+(.*)$", claim)
    if not m:
        return claim, False
    pron, rest = m.group(1), m.group(2)
    # only resolve when the next word is a verb (so "This approach ..." is left alone)
    nxt = _words(rest)[:1]
    if not nxt or not _is_verb(nxt[0]):
        return claim, False
    subj = prev_subject
    if pron in {"He", "She"} and not subj[:1].isupper():
        return claim, False
    return f"{_capitalize_first(subj)} {rest}", True


def clean_sentence(sentence: str) -> str:
    s = strip_citation_marks(sentence).strip()
    s = _DISCOURSE.sub("", s)
    return s.strip()


def is_checkable(sentence: str) -> bool:
    s = sentence.strip()
    if not s or s.endswith("?"):
        return False
    if _wc(s) < 3:
        return False
    if _META.match(s) or _OPINION_ONLY.match(s):
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    return True


def extract_claims(answer: str, *, split_compound: bool = True, resolve_pronouns: bool = True,
                   max_claims: int = 60) -> list[Claim]:
    """Extract atomic factual claims from an AI-generated answer."""
    text = normalize_text(answer or "")
    claims: list[Claim] = []
    prev_subject: str | None = None
    n = 0
    for sid, raw in enumerate(_sentences(text), start=1):
        cleaned = clean_sentence(raw)
        if not is_checkable(cleaned):
            continue
        parts = decompose(cleaned) if split_compound else [_finish(cleaned)]
        subject_here = _subject_phrase(cleaned)
        for part in parts:
            resolved = False
            if resolve_pronouns:
                part, resolved = _resolve_pronoun(part, prev_subject)
            if _wc(part) < 3:
                continue
            n += 1
            claims.append(Claim(
                id=f"C{n}", text=part, sentence_id=sid, sentence=raw.strip(), order=n,
                resolved_pronoun=resolved,
                context_note="Pronoun replaced using the previous sentence" if resolved else "",
            ))
            if n >= max_claims:
                return claims
        if subject_here:
            prev_subject = subject_here
    return claims


def claims_from_user(items: list[dict]) -> list[Claim]:
    """Build Claim objects from user-supplied (possibly edited) claims."""
    claims: list[Claim] = []
    for i, it in enumerate(items, start=1):
        text = (it.get("text") or "").strip()
        if not text:
            continue
        claims.append(Claim(
            id=it.get("id") or f"C{i}", text=text,
            sentence_id=int(it.get("sentence_id") or 0),
            sentence=it.get("sentence") or text, order=i,
            source=it.get("source") or "user",
            resolved_pronoun=bool(it.get("resolved_pronoun", False)),
            context_note=it.get("context_note") or "",
        ))
    # guarantee unique ids
    seen: set[str] = set()
    for c in claims:
        base, k = c.id, 1
        while c.id in seen:
            k += 1
            c.id = f"{base}_{k}"
        seen.add(c.id)
    return claims
