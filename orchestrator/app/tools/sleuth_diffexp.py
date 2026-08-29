"""A real sleuth MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript`
running sleuth's own canonical differential-expression workflow
(sleuth_prep -> sleuth_fit(~condition) -> sleuth_fit(~1) ->
sleuth_lrt -> sleuth_results), same pattern as `seurat_analyze`.
Gene mapping is fetched live from Ensembl. Requires a real uploaded
archive of per-sample Kallisto quant directories (format
`quant_dir_bundle`) AND a real uploaded design table mapping each
sample subdirectory name to its condition -- never fabricates a
sample's experimental group.
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

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "sleuth_diffexp.R")
MAX_ROWS_RETURNED = 30


def _run_sleuth(quant_root: Path, design_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(quant_root), str(design_path), str(out_path)],
        capture_output=True, text=True, timeout=1200,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "sleuth_differential_expression",
    "Given the filename of a real uploaded archive of per-sample "
    "Kallisto quant directories (see list_uploaded_files -- format "
    "`quant_dir_bundle`) and the filename of a real uploaded design "
    "table (a two-column TSV, no header: sample subdirectory "
    "name<TAB>condition, uploaded as a `table`), run sleuth's "
    "likelihood-ratio test to find genes differentially expressed "
    "across the given conditions. Never state a p-value or fold "
    "change this tool didn't actually compute, and never invent a "
    "sample's condition label.",
    {"filename": str, "design_filename": str},
)
async def sleuth_differential_expression(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    design_filename = (args.get("design_filename") or "").strip()
    updir = uploads_dir()
    if not filename or not design_filename or updir is None:
        return {"content": [{"type": "text", "text": "filename and design_filename must both be non-empty, and this experiment must have uploaded files."}]}

    file_path = updir / filename
    design_path = updir / design_filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}
    if not design_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {design_filename!r} in this experiment -- call list_uploaded_files first."}]}

    file_format = classify_upload(file_path)
    if file_format != "quant_dir_bundle":
        return {"content": [{"type": "text", "text": f"{filename!r} was detected as format `{file_format}`, not a Salmon/Kallisto quant directory bundle."}]}
    try:
        quant_root = extract_bundle(file_path)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return {"content": [{"type": "text", "text": f"Could not extract {filename!r}: {exc}"}]}

    out_path = updir / f"{filename}.{design_filename}.sleuth_results.csv"
    code, out, err = await asyncio.to_thread(_run_sleuth, quant_root, design_path, out_path)
    result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"sleuth differential expression failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": "sleuth ran but found no significant/testable genes."}]}

    lines = [f"sleuth differential expression for {filename} [sleuth:gene] -- {len(rows)} gene(s), ranked by ascending p-value:"]
    for row in rows[:MAX_ROWS_RETURNED]:
        gene = row.get("ext_gene") or row.get("target_id", "?")
        pval = row.get("pval", "?")
        qval = row.get("qval", "?")
        lines.append(f"- {gene}: p={pval}, q={qval}")
    if len(rows) > MAX_ROWS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_ROWS_RETURNED} more gene(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_sleuth_diffexp_mcp_server():
    return create_sdk_mcp_server(name="sleuth_diffexp", tools=[sleuth_differential_expression])
