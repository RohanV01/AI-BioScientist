"""A real SoupX MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript` running
SoupX's own canonical ambient-RNA-correction workflow (SoupChannel ->
setClusters -> autoEstCont -> adjustCounts), same pattern as
`seurat_analyze`. Needs both an unfiltered ("raw") and a
cell-called ("filtered") 10x matrix bundle from the same sample --
SoupX estimates the ambient RNA profile from empty droplets in the raw
matrix, which the filtered matrix alone doesn't contain.
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

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "soupx_correct.R")
MAX_ROWS_RETURNED = 25


def _run_soupx(raw_dir: Path, filtered_dir: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(raw_dir), str(filtered_dir), str(out_path)],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _resolve_mtx_dir(updir: Path, filename: str) -> tuple[Path | None, str | None]:
    path = updir / filename
    if not path.is_file():
        return None, f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."
    file_format = classify_upload(path)
    if file_format != "10x_mtx_bundle":
        return None, f"{filename!r} was detected as format `{file_format}`, not a 10x matrix.mtx+barcodes.tsv+features.tsv bundle."
    try:
        return extract_bundle(path), None
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return None, f"Could not extract {filename!r}: {exc}"


@tool(
    "soupx_correct_ambient_rna",
    "Given the filenames of two real uploaded 10x matrix bundles from "
    "the same sample -- an unfiltered/raw bundle (all droplets, "
    "including empty ones) and a filtered/cell-called bundle (see "
    "list_uploaded_files, both must have format `10x_mtx_bundle`) -- "
    "run SoupX to estimate and remove ambient RNA contamination. "
    "Reports the estimated contamination fraction and the genes with "
    "the most counts removed. Never state a contamination estimate "
    "this tool didn't actually compute.",
    {"raw_filename": str, "filtered_filename": str},
)
async def soupx_correct_ambient_rna(args: dict[str, Any]) -> dict[str, Any]:
    raw_filename = (args.get("raw_filename") or "").strip()
    filtered_filename = (args.get("filtered_filename") or "").strip()
    updir = uploads_dir()
    if not raw_filename or not filtered_filename or updir is None:
        return {"content": [{"type": "text", "text": "raw_filename and filtered_filename must both be non-empty, and this experiment must have uploaded files."}]}

    raw_dir, err = _resolve_mtx_dir(updir, raw_filename)
    if err:
        return {"content": [{"type": "text", "text": err}]}
    filtered_dir, err = _resolve_mtx_dir(updir, filtered_filename)
    if err:
        return {"content": [{"type": "text", "text": err}]}

    out_path = updir / f"{raw_filename}.{filtered_filename}.soupx_result.csv"
    code, out, err_text = await asyncio.to_thread(_run_soupx, raw_dir, filtered_dir, out_path)
    result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"SoupX correction failed: {err_text.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": "SoupX ran but produced no per-gene rows."}]}

    contamination = rows[0].get("estimated_contamination_fraction", "?")
    lines = [f"SoupX ambient RNA correction [soupx:gene] -- estimated contamination fraction: {contamination}"]
    lines.append("Top genes by ambient counts removed:")
    for row in rows[:MAX_ROWS_RETURNED]:
        gene = row.get("gene", "?")
        removed = row.get("counts_removed", "?")
        pct = row.get("pct_removed", "?")
        lines.append(f"- {gene}: {removed} counts removed ({pct}%)")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_soupx_correct_mcp_server():
    return create_sdk_mcp_server(name="soupx_correct", tools=[soupx_correct_ambient_rna])
