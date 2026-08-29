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
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.experiment_context import uploads_dir
from app.file_uploads import classify_upload

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


def build_experiment_uploads_mcp_server():
    return create_sdk_mcp_server(name="experiment_uploads", tools=[list_uploaded_files])
