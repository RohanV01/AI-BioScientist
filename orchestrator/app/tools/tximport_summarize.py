"""A real tximport MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript`
running tximport's own canonical workflow, same pattern as
`seurat_analyze`. Transcript-to-gene mapping is fetched live from
Ensembl (via biomaRt, inside the R script) for exactly the transcript
IDs in the uploaded quant files -- no baked-in tx2gene snapshot.
Expects a real uploaded archive containing one Salmon/Kallisto quant
subdirectory per sample (classified as `quant_dir_bundle` by
app/file_uploads.py).
"""
import asyncio
import csv
import io
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.experiment_context import uploads_dir
from app.file_uploads import classify_upload, extract_bundle

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "tximport_summarize.R")
MAX_ROWS_RETURNED = 30


def _run_tximport(quant_root: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(quant_root), str(out_path)],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "tximport_summarize_quants",
    "Given the filename of a real uploaded archive containing one "
    "Salmon or Kallisto quantification subdirectory per sample (see "
    "list_uploaded_files -- format `quant_dir_bundle`), run tximport "
    "to summarize transcript-level quantifications to gene-level "
    "counts, using a transcript-to-gene mapping looked up live from "
    "Ensembl. Never state a gene count this tool didn't actually "
    "compute.",
    {"filename": str},
)
async def tximport_summarize_quants(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    updir = uploads_dir()
    if not filename or updir is None:
        return {"content": [{"type": "text", "text": "filename must be non-empty, and this experiment must have an uploaded file."}]}
    file_path = updir / filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}

    file_format = classify_upload(file_path)
    if file_format != "quant_dir_bundle":
        return {"content": [{"type": "text", "text": f"{filename!r} was detected as format `{file_format}`, not a Salmon/Kallisto quant directory bundle."}]}
    try:
        quant_root = extract_bundle(file_path)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return {"content": [{"type": "text", "text": f"Could not extract {filename!r}: {exc}"}]}

    out_path = updir / f"{filename}.tximport_genes.csv"
    code, out, err = await asyncio.to_thread(_run_tximport, quant_root, out_path)
    result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"tximport summarization failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": f"tximport found no gene-level rows in {filename}."}]}

    sample_cols = [c for c in rows[0].keys() if c != "gene"]
    lines = [f"tximport gene-level summarization for {filename} [tximport:gene] -- {len(rows)} gene(s) across sample(s): {', '.join(sample_cols)}"]
    for row in rows[:MAX_ROWS_RETURNED]:
        counts = ", ".join(f"{c}={row.get(c, '?')}" for c in sample_cols)
        lines.append(f"- {row.get('gene', '?')}: {counts}")
    if len(rows) > MAX_ROWS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_ROWS_RETURNED} more gene(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_tximport_summarize_mcp_server():
    return create_sdk_mcp_server(name="tximport_summarize", tools=[tximport_summarize_quants])
