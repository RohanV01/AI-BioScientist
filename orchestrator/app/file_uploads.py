"""Real file-upload pipeline for the R-bridge's data-gated tools
(docs/17-remaining-tools-wiring-plan.md Phase 3 -- Seurat, dada2,
SoupX, monocle, InferCNV, Giotto, tximport, sleuth). Mattermost's real
Outgoing Webhook payload includes a `file_ids` field (confirmed against
Mattermost's own server source, `OutgoingWebhookPayload.FileIds` in
server/public/model/outgoing_webhook.go) -- a comma-separated list of
file IDs attached to the triggering post. This module downloads those
real files (via `MattermostClient.download_file`, real
`GET /api/v4/files/{id}`) into the current experiment's own
`uploads/` folder and classifies each by real format so the master
agent's `list_uploaded_files` tool (app/tools/experiment_uploads.py)
can tell the researcher what's usable and by which tool.

Kept out of app/routers/mattermost_webhook.py itself (which just calls
`handle_uploaded_files` once per task) -- same separation as
app/experiment_synthesis.py from that router.
"""
import logging
import tarfile
import zipfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.mattermost_client import MattermostClient
from app.models import Attachment
from app.text_extraction import extract_text_content

logger = logging.getLogger(__name__)

# Real, sniffable format classes each downstream R tool expects --
# confirmed against each tool's own documented input requirements
# before wiring the tools themselves (see each app/tools/*.py file).
FASTQ_EXTENSIONS = {".fastq", ".fq", ".fastq.gz", ".fq.gz"}
H5_MATRIX_EXTENSIONS = {".h5", ".h5ad", ".loom"}
ARCHIVE_EXTENSIONS = {".tar.gz", ".tgz", ".zip"}
TABLE_EXTENSIONS = {".csv", ".tsv", ".txt"}
# General-document formats, added for the multi-stage research pipeline
# plan's ingestion stage -- distinct from TABLE_EXTENSIONS' tabular .txt
# handling (a delimited data file), so a plain prose .txt/.md doesn't get
# misclassified as "table".
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}
PROSE_TEXT_EXTENSIONS = {".txt", ".md"}


def _looks_tabular(path: Path) -> bool:
    """A .txt is "table" only if it actually looks delimited -- a
    consistent comma/tab field-count across its first several non-blank
    lines. Anything else (prose, notes, a README) is "text_document" so
    extract_text_content actually reads it instead of an R-bridge tool
    silently trying to parse prose as a data table."""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()][:10]
    except OSError:
        return False
    if len(lines) < 2:
        return False
    for delimiter in (",", "\t"):
        counts = {ln.count(delimiter) for ln in lines}
        if len(counts) == 1 and counts != {0}:
            return True
    return False


def _matches_suffix(name: str, suffixes: set[str]) -> bool:
    lower = name.lower()
    return any(lower.endswith(s) for s in suffixes)


def _classify_archive_contents(names: list[str]) -> str:
    lower_names = [n.lower() for n in names]
    has_mtx = any(n.endswith("matrix.mtx") or n.endswith("matrix.mtx.gz") for n in lower_names)
    has_barcodes = any("barcodes.tsv" in n for n in lower_names)
    has_features = any("features.tsv" in n or "genes.tsv" in n for n in lower_names)
    if has_mtx and has_barcodes and has_features:
        return "10x_mtx_bundle"
    has_quant_sf = any(n.endswith("quant.sf") for n in lower_names)
    has_abundance = any(n.endswith("abundance.tsv") or n.endswith("abundance.h5") for n in lower_names)
    if has_quant_sf or has_abundance:
        return "quant_dir_bundle"
    return "unrecognized_archive"


def classify_upload(path: Path) -> str:
    """Real format classification by extension + (for archives) real
    content listing -- never guessed from the filename alone for an
    archive, since "data.zip" tells you nothing about what's inside."""
    name = path.name
    if _matches_suffix(name, FASTQ_EXTENSIONS):
        return "fastq"
    if _matches_suffix(name, H5_MATRIX_EXTENSIONS):
        return "10x_h5_matrix"
    if name.lower().endswith((".tar.gz", ".tgz")):
        try:
            with tarfile.open(path, "r:gz") as tf:
                return _classify_archive_contents(tf.getnames())
        except tarfile.TarError:
            return "unrecognized_archive"
    if name.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                return _classify_archive_contents(zf.namelist())
        except zipfile.BadZipFile:
            return "unrecognized_archive"
    if _matches_suffix(name, PDF_EXTENSIONS):
        return "pdf_document"
    if _matches_suffix(name, DOCX_EXTENSIONS):
        return "docx_document"
    if _matches_suffix(name, PROSE_TEXT_EXTENSIONS) and not _looks_tabular(path):
        return "text_document"
    if _matches_suffix(name, TABLE_EXTENSIONS):
        return "table"
    return "unknown"


def extract_bundle(archive_path: Path) -> Path:
    """Real extraction for a 10x mtx trio / Salmon-Kallisto quant
    directory bundle -- shared by every R-bridge tool that consumes one
    (seurat_analyze, soupx_correct, tximport_summarize,
    sleuth_differential_expression), so the extraction logic and its
    real edge case (a single top-level folder inside the archive,
    common for a directory someone just zipped up) is handled once.
    Idempotent -- returns the existing extraction dir if already done."""
    extract_dir = archive_path.parent / f"{archive_path.name}.extracted"
    if extract_dir.is_dir() and any(extract_dir.iterdir()):
        return _real_content_root(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    name = archive_path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(extract_dir, filter="data")
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
    else:
        raise ValueError(f"{archive_path.name} is not a supported archive format (.tar.gz/.tgz/.zip).")

    return _real_content_root(extract_dir)


def _real_content_root(extract_dir: Path) -> Path:
    """If the archive contained one single top-level directory (the
    common case for "zip up my results folder"), the real content the
    caller wants is one level in -- confirmed against how 10x/Salmon/
    Kallisto output is typically bundled, not assumed."""
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


_GENERAL_DOCUMENT_FORMATS = {"pdf_document", "docx_document", "text_document"}


async def handle_uploaded_files(
    mm: MattermostClient,
    file_ids: list[str],
    experiment_dir: Path,
    db: AsyncSession | None = None,
    experiment_id=None,
    task_id=None,
) -> list[dict]:
    """Download every real file attached to the triggering Mattermost
    post into <experiment_dir>/uploads/, and classify each. Returns a
    list of {filename, size, format, path} -- the same shape
    list_uploaded_files reads back later, so a caller can also post an
    immediate summary. Never fabricates a format for a file it
    couldn't actually download or open.

    Multi-stage research pipeline plan, ingestion stage: when `db` +
    `experiment_id` are supplied, also runs text extraction for general
    document formats (writing a `<filename>.extracted.txt` sidecar the new
    read_ingested_content tool serves back) and persists one Attachment row
    per file -- the audit trail app/models.py's Attachment closes. Callers
    with no live experiment (none exist today, but kept optional rather
    than required so a future standalone/test call isn't forced into a real
    DB session just to download files) get the old behavior unchanged."""
    uploads_dir = experiment_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file_id in file_ids:
        file_id = file_id.strip()
        if not file_id:
            continue
        try:
            info = await mm.get_file_info(file_id)
            filename = info.get("name", file_id)
            content = await mm.download_file(file_id)
        except Exception as exc:  # noqa: BLE001 -- a failed download for one file must not lose the others
            logger.warning("Failed to download Mattermost file %s: %s", file_id, exc)
            results.append({"filename": file_id, "size": None, "format": "download_failed", "path": None})
            if db is not None and experiment_id is not None:
                db.add(Attachment(
                    experiment_id=experiment_id, task_id=task_id, source_type="mattermost_file",
                    original_ref=file_id, filename_or_title=None, detected_format="download_failed",
                    storage_path="", extraction_status="failed",
                ))
            continue

        dest_path = uploads_dir / filename
        dest_path.write_bytes(content)
        file_format = classify_upload(dest_path)
        results.append({"filename": filename, "size": len(content), "format": file_format, "path": str(dest_path)})

        if db is not None and experiment_id is not None:
            extraction_status = "unsupported_format"
            if file_format in _GENERAL_DOCUMENT_FORMATS:
                text = extract_text_content(dest_path, file_format)
                if text is not None:
                    dest_path.with_suffix(dest_path.suffix + ".extracted.txt").write_text(text)
                    extraction_status = "ok"
                else:
                    extraction_status = "unreadable"
            db.add(Attachment(
                experiment_id=experiment_id, task_id=task_id, source_type="mattermost_file",
                original_ref=file_id, filename_or_title=filename, detected_format=file_format,
                storage_path=str(dest_path), extraction_status=extraction_status,
            ))

    return results
