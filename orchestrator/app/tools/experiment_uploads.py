"""Real tool for the master agent to discover files a researcher
actually uploaded to the current experiment (docs/17-remaining-tools-
wiring-plan.md Phase 3's file-upload pipeline -- see app/file_uploads.py
for how they get there). Deliberately a real tool call, not context
injected straight into the prompt: this platform's whole grounding
model is "every fact the agent uses traces to a real tool call," and a
researcher's uploaded data is no exception -- the agent has to call
this to learn what's available, same as it has to call pubmed/chembl/
etc. for anything else.
"""
import hashlib
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.experiment_context import uploads_dir
from app.file_uploads import classify_upload

# Tool-output truncation, distinct from text_extraction.py's extraction-time
# cap (200k chars) -- what actually gets read back into the agent's context
# in one call needs to be smaller than what's kept on disk.
_MAX_TOOL_OUTPUT_CHARS = 20_000

FORMAT_DESCRIPTIONS = {
    "fastq": "raw sequencing reads -- usable with dada2_denoise_amplicons",
    "10x_h5_matrix": "a 10x-format count matrix (.h5/.h5ad/.loom) -- usable with seurat_analyze_scrna, monocle_pseudotime, infercnv_analyze",
    "10x_mtx_bundle": "a 10x raw matrix.mtx/barcodes.tsv/features.tsv bundle -- usable with seurat_analyze_scrna, soupx_correct_ambient_rna",
    "quant_dir_bundle": "a Salmon/Kallisto quantification directory -- usable with tximport_summarize, sleuth_differential_expression",
    "table": "a plain CSV/TSV table -- may be a count matrix or spatial coordinates depending on content",
    "unrecognized_archive": "an archive that doesn't match any known bundle format (10x matrix trio or Salmon/Kallisto quant output)",
    "unknown": "unrecognized file type",
    "download_failed": "this file failed to download from Mattermost -- ask the researcher to re-upload it",
}


@tool(
    "list_uploaded_files",
    "List every file the researcher has actually uploaded to this "
    "experiment (via a Mattermost message attachment), with its real "
    "detected format and which R-bridge tool(s) it's usable with. Call "
    "this before using any tool that needs a researcher-supplied file "
    "(dada2_denoise_amplicons, seurat_analyze_scrna, "
    "soupx_correct_ambient_rna, monocle_pseudotime, infercnv_analyze, "
    "giotto_spatial_analysis, tximport_summarize, "
    "sleuth_differential_expression) -- never assume a file exists or "
    "guess its path.",
    {},
)
async def list_uploaded_files(args: dict[str, Any]) -> dict[str, Any]:
    updir = uploads_dir()
    if updir is None or not updir.is_dir():
        return {"content": [{"type": "text", "text": "No files have been uploaded to this experiment yet."}]}

    files = sorted(p for p in updir.iterdir() if p.is_file())
    if not files:
        return {"content": [{"type": "text", "text": "No files have been uploaded to this experiment yet."}]}

    lines = [f"Uploaded files in this experiment [experiment_uploads:file] -- {len(files)} file(s):"]
    for path in files:
        file_format = classify_upload(path)
        size = path.stat().st_size
        description = FORMAT_DESCRIPTIONS.get(file_format, file_format)
        lines.append(f"- {path.name} ({size} bytes): format=`{file_format}` -- {description}\n  path: {path}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _find_sidecar(filename_or_url: str) -> Path | None:
    """A file's sidecar sits next to it as `<name>.extracted.txt`
    (app/file_uploads.py's convention); a URL's sidecar sits under
    uploads/links/<hash>.extracted.txt (app/link_ingestion.py's convention,
    same hash: first 16 hex chars of sha256(url))."""
    updir = uploads_dir()
    if updir is None:
        return None

    if filename_or_url.startswith("http://") or filename_or_url.startswith("https://"):
        url_hash = hashlib.sha256(filename_or_url.encode()).hexdigest()[:16]
        candidate = updir / "links" / f"{url_hash}.extracted.txt"
        return candidate if candidate.is_file() else None

    for path in updir.glob("*.extracted.txt"):
        # path.name is "<original filename>.extracted.txt" -- strip that
        # suffix to compare against the plain filename the agent knows about.
        if path.name[: -len(".extracted.txt")] == filename_or_url:
            return path
    return None


@tool(
    "read_ingested_content",
    "Read the actual extracted text of an uploaded document (PDF/DOCX/plain "
    "text) or a pasted URL that was fetched for this experiment -- pass the "
    "exact filename (as shown by list_uploaded_files) or the exact URL. "
    "This is what makes ingested content genuinely usable, not just listed "
    "by name; a large document may be truncated with a note if it exceeds "
    "the per-call length cap.",
    {"filename_or_url": str},
)
async def read_ingested_content(args: dict[str, Any]) -> dict[str, Any]:
    sidecar = _find_sidecar(args["filename_or_url"])
    if sidecar is None:
        return {
            "content": [{
                "type": "text",
                "text": f"No extracted content found for {args['filename_or_url']!r} -- it may not have been "
                        "ingested, or extraction failed (an unreadable/scanned file, or an unfetchable URL). "
                        "Call list_uploaded_files to see what's actually available.",
            }]
        }

    text = sidecar.read_text()
    if len(text) > _MAX_TOOL_OUTPUT_CHARS:
        text = text[:_MAX_TOOL_OUTPUT_CHARS] + "\n\n[... more content available, truncated for this call ...]"
    return {"content": [{"type": "text", "text": f"[experiment_uploads:{args['filename_or_url']}]\n\n{text}"}]}


def build_experiment_uploads_mcp_server():
    return create_sdk_mcp_server(name="experiment_uploads", tools=[list_uploaded_files, read_ingested_content])
