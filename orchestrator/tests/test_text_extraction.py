"""Real tests for app/text_extraction.py -- actual pymupdf/python-docx
extraction against real files, no mocking."""
import docx
import pymupdf

from app.text_extraction import extract_pdf_text, extract_text_content


def _make_real_pdf(path, text: str):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _make_real_docx(path, text: str):
    document = docx.Document()
    document.add_paragraph(text)
    document.save(path)


def test_extract_pdf_text_reads_real_content(tmp_path):
    p = tmp_path / "paper.pdf"
    _make_real_pdf(p, "EGFR resistance mutation T790M")
    text = extract_pdf_text(p)
    assert "EGFR" in text


def test_extract_text_content_pdf(tmp_path):
    p = tmp_path / "paper.pdf"
    _make_real_pdf(p, "KRAS G12C inhibitor sotorasib")
    text = extract_text_content(p, "pdf_document")
    assert text is not None
    assert "KRAS" in text


def test_extract_text_content_docx(tmp_path):
    p = tmp_path / "notes.docx"
    _make_real_docx(p, "Research notes on BRCA1 variant classification.")
    text = extract_text_content(p, "docx_document")
    assert text is not None
    assert "BRCA1" in text


def test_extract_text_content_plain_text(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Plain prose about TP53.")
    text = extract_text_content(p, "text_document")
    assert text == "Plain prose about TP53."


def test_extract_text_content_unsupported_format_returns_none(tmp_path):
    p = tmp_path / "reads.fastq"
    p.write_text("@read1\nACGT\n+\nIIII\n")
    assert extract_text_content(p, "fastq") is None


def test_extract_text_content_corrupt_pdf_returns_none_not_raises(tmp_path):
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"not a real pdf at all")
    assert extract_text_content(p, "pdf_document") is None


def test_extract_text_content_truncates_past_cap(tmp_path, monkeypatch):
    import app.text_extraction as te

    monkeypatch.setattr(te, "_MAX_EXTRACTION_CHARS", 20)
    p = tmp_path / "long.txt"
    p.write_text("x" * 100)
    text = extract_text_content(p, "text_document")
    assert text is not None
    assert "truncated" in text
    assert len(text) < 100
