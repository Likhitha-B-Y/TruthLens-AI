"""Shared text helpers: normalisation, sentence splitting, hashing, tokenisation."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache

from nltk.stem import PorterStemmer

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "inc", "ltd", "co", "corp",
    "no", "fig", "figs", "approx", "dept", "est", "u.s", "u.k", "u.s.a", "ph.d", "a.m", "p.m", "cf", "al",
    "gen", "gov", "sen", "rep", "col", "lt", "capt", "sgt", "mt", "ft", "jan", "feb", "mar", "apr", "jun",
    "jul", "aug", "sep", "sept", "oct", "nov", "dec", "vol", "ed", "eds", "pp", "ca", "c", "v",
}

_BOUNDARY = re.compile(r"""([.!?]+["')\]]*)\s+(?=["'(\[]?[A-Z0-9])""")
_PARA_SPLIT = re.compile(r"\n\s*\n|\n(?=\s*(?:[-*\u2022]|\d{1,2}[.)])\s)")
_LEADING_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d{1,2}[.)])\s+")
_CITATION_MARKS = re.compile(r"\s*\[(?:\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*)\]")


def normalize_text(text: str) -> str:
    """Unicode-normalise and clean extracted text while keeping paragraph breaks."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")                      # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # de-hyphenate line wraps
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # remove control characters except newline
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    return text.strip()


def strip_citation_marks(text: str) -> str:
    return _CITATION_MARKS.sub("", text)


def split_sentences(text: str) -> list[str]:
    """Rule-based sentence splitter that handles abbreviations, initials and decimals."""
    sentences: list[str] = []
    for para in _PARA_SPLIT.split(text):
        para = _LEADING_BULLET.sub("", para)
        para = " ".join(para.split())
        if not para:
            continue
        start = 0
        for m in _BOUNDARY.finditer(para):
            punct = m.group(1)
            before = para[start:m.start(1)]
            token_match = re.search(r"(\S+)$", before)
            token = token_match.group(1) if token_match else ""
            if punct == ".":
                bare = token.strip("\"'([").rstrip(".").lower()
                if bare in _ABBREVIATIONS:
                    continue
                if re.fullmatch(r"[A-Z]", token.strip("\"'([")):             # initial: J. K. Rowling
                    continue
                if re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", token.strip("\"'([")):   # U.S.A
                    continue
            end = m.end(1)
            s = para[start:end].strip()
            if s:
                sentences.append(s)
            start = m.end()
        tail = para[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def word_count(text: str) -> int:
    return len(text.split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------- tokenising for BM25
_STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been before being below between both
    but by can did do does doing down during each few for from further had has have having he her here hers herself
    him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only
    or other our ours ourselves out over own same she should so some such than that the their theirs them themselves
    then there these they this those through to too under until up very was we were what when where which while who
    whom why will with would you your yours yourself yourselves also however""".split()
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.'][A-Za-z0-9]+)*")
_stemmer = PorterStemmer()


@lru_cache(maxsize=100_000)
def _stem(token: str) -> str:
    return _stemmer.stem(token)


def tokenize(text: str, remove_stopwords: bool = True, stem: bool = True) -> list[str]:
    toks = [t.lower().replace("'", "") for t in _TOKEN_RE.findall(text)]
    if remove_stopwords:
        toks = [t for t in toks if t not in _STOPWORDS]
    if stem:
        toks = [_stem(t) for t in toks]
    return toks


def content_words(text: str) -> set[str]:
    return set(tokenize(text))
