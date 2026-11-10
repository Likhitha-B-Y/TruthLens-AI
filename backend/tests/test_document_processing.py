import pytest

from app.services.document_processing import (DocumentError, chunk_pages, extract_document, safe_filename)
from conftest import SAMPLES


def test_extract_txt():
    d = extract_document(SAMPLES / "eiffel_tower_factsheet.txt")
    assert d.ext == ".txt" and d.pages[0][0] == 1
    assert "Gustave Eiffel" in d.pages[0][1]


def test_extract_pdf_keeps_page_numbers():
    d = extract_document(SAMPLES / "solar_system_notes.pdf")
    assert [p for p, _ in d.pages] == [1, 2]
    assert "Mercury" in d.pages[0][1] and "Jupiter" in d.pages[1][1]
    assert "Jupiter" not in d.pages[0][1]


def test_extract_docx_uses_page_breaks_and_metadata():
    d = extract_document(SAMPLES / "photosynthesis_overview.docx")
    assert [p for p, _ in d.pages] == [1, 2]
    assert "chloroplasts" in d.pages[0][1] and "Calvin cycle" in d.pages[1][1]
    assert d.meta["title"] == "Photosynthesis: An Overview"


def test_empty_and_unsupported_files(tmp_path):
    e = tmp_path / "empty.txt"
    e.write_text("   \n  ")
    with pytest.raises(DocumentError):
        extract_document(e)
    x = tmp_path / "a.xyz"
    x.write_text("hello")
    with pytest.raises(DocumentError, match="Unsupported"):
        extract_document(x)


def test_corrupt_pdf_and_docx(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(DocumentError):
        extract_document(bad)
    bad2 = tmp_path / "bad.docx"
    bad2.write_bytes(b"not a docx")
    with pytest.raises(DocumentError):
        extract_document(bad2)


def test_txt_encoding_fallback(tmp_path):
    p = tmp_path / "latin.txt"
    p.write_bytes("Caf\xe9 de Paris is a restaurant in the city.".encode("latin-1"))
    assert "Café" in extract_document(p).pages[0][1]


def test_text_cleaning_dehyphenates(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("The infor-\nmation is   clean.\n\n\n\nNext paragraph here.")
    t = extract_document(p).pages[0][1]
    assert "information is clean." in t and "\n\n\n" not in t


def test_chunking_overlaps_and_never_crosses_pages():
    s = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(30))
    pages = [(1, s), (2, "Second page sentence one. Second page sentence two.")]
    chunks = chunk_pages(pages, chunk_words=40, overlap_sentences=1)
    assert len({c.page for c in chunks}) == 2
    p1 = [c for c in chunks if c.page == 1]
    assert len(p1) > 2
    # consecutive passages share the last sentence of the previous one
    assert p1[0].text.split(". ")[-1].strip(". ") in p1[1].text
    assert all(len(c.text.split()) <= 60 for c in chunks)
    assert all(c.page == 2 for c in chunks if "Second page" in c.text)


def test_chunking_handles_one_huge_sentence():
    chunks = chunk_pages([(1, " ".join(f"w{i}" for i in range(700)))], chunk_words=100, overlap_sentences=1)
    assert len(chunks) >= 3 and all(len(c.text.split()) <= 101 for c in chunks)


def test_safe_filename():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("my file (1).pdf") == "my file _1_.pdf"
