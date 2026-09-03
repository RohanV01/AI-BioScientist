"""General document text extraction, shared by app/tools/literature_discovery.py's
read_paper (paper PDFs downloaded via download_paper) and the ingestion
stage's handle_uploaded_files (arbitrary researcher-supplied files) -- one
place to know how to pull real text out of a PDF/DOCX/plain-text file,
instead of duplicating pymupdf-handling in two modules.

`extract_text_content` never fabricates text for a file it couldn't
actually read (a scanned-image PDF, a corrupt DOCX) -- it returns None,
same "don't guess" discipline as app/file_uploads.py's classify_upload.
"""
from pathlib import Path

import pymupdf

# Same length discipline read_paper's structured-extraction call already
# needs (a very long PDF/DOCX otherwise blows the LLM context on ingestion
# steps that read this sidecar back) -- one shared cap rather than a
# per-caller guess.
_MAX_EXTRACTION_CHARS = 200_000


def extract_pdf_text(pdf_path: Path) -> str:
    """Moved here from app/tools/literature_discovery.py's former
    module-private _extract_pdf_text -- same real pymupdf extraction, now
    shared instead of duplicated for the ingestion stage's own PDF uploads."""
    doc = pymupdf.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _extract_docx_text(docx_path: Path) -> str:
    import docx  # python-docx -- imported lazily, same reasoning as llm_backend's per-backend lazy imports

    document = docx.Document(docx_path)
    return "\n".join(p.text for p in document.paragraphs)


def _extract_plain_text(text_path: Path) -> str:
    return text_path.read_text(encoding="utf-8", errors="replace")


def extract_text_content(path: Path, file_format: str) -> str | None:
    """Dispatches on the format app/file_uploads.py's classify_upload
    already determined. Returns None (never an empty string standing in for
    "unreadable") when extraction genuinely produced nothing or the format
    isn't one this module knows how to read -- the caller decides how to
    report that (see handle_uploaded_files' extraction_status)."""
    try:
        if file_format == "pdf_document":
            text = extract_pdf_text(path)
        elif file_format == "docx_document":
            text = _extract_docx_text(path)
        elif file_format == "text_document":
            text = _extract_plain_text(path)
        else:
            return None
    except Exception:  # noqa: BLE001 -- a corrupt/unreadable file must not crash ingestion for the rest of the batch
        return None

    text = text.strip()
    if not text:
        return None
    if len(text) > _MAX_EXTRACTION_CHARS:
        text = text[:_MAX_EXTRACTION_CHARS] + "\n\n[... truncated, extraction exceeded the length cap ...]"
    return text
