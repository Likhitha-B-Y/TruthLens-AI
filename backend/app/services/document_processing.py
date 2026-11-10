"""Document extraction (PDF / DOCX / TXT) and overlapping passage chunking."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .text_utils import normalize_text, sha256_text, split_sentences

log = logging.getLogger(__name__)


class DocumentError(Exception):
    """Raised when a document cannot be read or contains no usable text."""


@dataclass
class ExtractedDocument:
    name: str
    ext: str
    pages: list[tuple[int, str]]            # (1-based page number, cleaned text)
    meta: dict = field(default_factory=dict)


# ------------------------------------------------------------------ extraction
def extract_pdf(path: Path) -> ExtractedDocument:
    try:
        import pymupdf  # PyMuPDF >= 1.24 name
    except ImportError:  # pragma: no cover - older installs
        import fitz as pymupdf  # type: ignore

    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        raise DocumentError(f"Could not open PDF: {e}") from e
    try:
        if doc.is_encrypted and not doc.authenticate(""):
            raise DocumentError("PDF is password-protected. Remove the password and upload again.")
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(doc, start=1):
            txt = normalize_text(page.get_text("text"))
            if txt:
                pages.append((i, txt))
        md = doc.metadata or {}
        meta = {
            "title": (md.get("title") or "").strip(),
            "author": (md.get("author") or "").strip(),
            "total_pages": doc.page_count,
        }
    finally:
        doc.close()
    if not pages:
        raise DocumentError(
            "No extractable text found. This looks like a scanned/image-only PDF; OCR is not supported."
        )
    return ExtractedDocument(path.name, ".pdf", pages, meta)


def extract_docx(path: Path) -> ExtractedDocument:
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as e:  # pragma: no cover
        raise DocumentError("python-docx is not installed.") from e

    try:
        d = docx.Document(str(path))
    except Exception as e:
        raise DocumentError(f"Could not open DOCX: {e}") from e

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    pages: dict[int, list[str]] = {1: []}
    current = 1
    for child in d.element.body.iterchildren():
        if child.tag == f"{W}p":
            para = Paragraph(child, d)
            # explicit page breaks / Word's rendered page break markers advance the page counter
            n_breaks = sum(1 for br in child.iter(f"{W}br") if br.get(f"{W}type") == "page")
            n_breaks += sum(1 for _ in child.iter(f"{W}lastRenderedPageBreak"))
            text = para.text.strip()
            if n_breaks and not text:
                current += n_breaks
                pages.setdefault(current, [])
                continue
            if n_breaks:
                current += n_breaks
                pages.setdefault(current, [])
            if text:
                pages[current].append(text)
        elif child.tag == f"{W}tbl":
            table = Table(child, d)
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    t = " ".join(cell.text.split())
                    if t and (not cells or cells[-1] != t):
                        cells.append(t)
                if cells:
                    pages[current].append(" | ".join(cells))
    out = [(p, normalize_text("\n\n".join(parts))) for p, parts in sorted(pages.items()) if parts]
    out = [(p, t) for p, t in out if t]
    if not out:
        raise DocumentError("The DOCX file contains no text.")
    cp = d.core_properties
    meta = {"title": (cp.title or "").strip(), "author": (cp.author or "").strip(),
            "page_note": "DOCX has no fixed pagination; page numbers follow page breaks stored in the file."}
    return ExtractedDocument(path.name, ".docx", out, meta)


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):          # UTF-16 only when a BOM says so
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            pass
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")  # pragma: no cover


def extract_txt(path: Path) -> ExtractedDocument:
    text = _read_text_file(path)
    chunks = text.split("\f") if "\f" in text else [text]       # form feed = page break
    pages = [(i, normalize_text(c)) for i, c in enumerate(chunks, start=1)]
    pages = [(i, t) for i, t in pages if t]
    if not pages:
        raise DocumentError("The text file is empty.")
    return ExtractedDocument(path.name, ".txt", pages, {"title": ""})


def extract_document(path: Path, display_name: str | None = None) -> ExtractedDocument:
    ext = path.suffix.lower()
    if ext == ".pdf":
        doc = extract_pdf(path)
    elif ext == ".docx":
        doc = extract_docx(path)
    elif ext == ".txt":
        doc = extract_txt(path)
    else:
        raise DocumentError(f"Unsupported file type '{ext}'. Upload PDF, DOCX or TXT.")
    if display_name:
        doc.name = display_name
    return doc


# ------------------------------------------------------------------- chunking
@dataclass
class PassageDraft:
    page: int
    idx: int
    text: str
    text_hash: str


def _hard_split(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def chunk_pages(pages: list[tuple[int, str]], chunk_words: int = 120, overlap_sentences: int = 1) -> list[PassageDraft]:
    """Split page text into overlapping, sentence-aligned passages.

    Passages never cross page boundaries so every citation has an exact page number.
    Each passage targets ~`chunk_words` words; consecutive passages share `overlap_sentences`.
    """
    drafts: list[PassageDraft] = []
    idx = 0
    for page_no, text in pages:
        sents: list[str] = []
        for s in split_sentences(text):
            if len(s.split()) > chunk_words * 2:
                sents.extend(_hard_split(s, chunk_words))
            else:
                sents.append(s)
        if not sents:
            continue
        counts = [len(s.split()) for s in sents]
        i = 0
        while i < len(sents):
            j, total = i, 0
            while j < len(sents) and (total + counts[j] <= chunk_words or j == i):
                total += counts[j]
                j += 1
            passage = " ".join(sents[i:j]).strip()
            if passage:
                drafts.append(PassageDraft(page_no, idx, passage, sha256_text(passage)))
                idx += 1
            if j >= len(sents):
                break
            nxt = j - overlap_sentences
            i = nxt if nxt > i else j          # always make progress
    # drop exact duplicates (e.g. repeated headers) while keeping order
    seen: set[str] = set()
    unique = []
    for d in drafts:
        if d.text_hash in seen:
            continue
        seen.add(d.text_hash)
        unique.append(d)
    return unique


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str) -> str:
    name = Path(name).name                       # strip any directory components
    name = _SAFE_NAME.sub("_", name).strip(" .")
    return name or "document"
