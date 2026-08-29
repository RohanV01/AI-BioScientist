"""A real Monocle3 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript`
running Monocle3's own canonical pseudotime workflow
(new_cell_data_set -> preprocess_cds -> reduce_dimension ->
cluster_cells -> learn_graph -> order_cells), same pattern as
`seurat_analyze`. Requires a real root-cell barcode from the dataset
(e.g. from a prior `seurat_analyze_scrna` call on the same upload) --
never invents or auto-guesses a root, since pseudotime=0 has no
principled definition without one.
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

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "monocle_pseudotime.R")
MAX_ROWS_RETURNED = 25


def _run_monocle(input_path: Path, input_type: str, root_cell: str, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(input_path), input_type, root_cell, str(out_path)],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "monocle_pseudotime_trajectory",
    "Given the filename of a real uploaded single-cell RNA-seq count "
    "matrix (see list_uploaded_files -- format `10x_h5_matrix` or "
    "`10x_mtx_bundle`) and a real root_cell barcode from that same "
    "matrix (get one from seurat_analyze_scrna's cluster output "
    "first), run Monocle3 to learn a trajectory graph and compute each "
    "cell's pseudotime distance from that root. Never state a "
    "pseudotime value this tool didn't actually compute, and never "
    "invent a root_cell barcode -- it must be a real barcode from the "
    "dataset.",
    {"filename": str, "root_cell": str},
)
async def monocle_pseudotime_trajectory(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    root_cell = (args.get("root_cell") or "").strip()
    updir = uploads_dir()
    if not filename or not root_cell or updir is None:
        return {"content": [{"type": "text", "text": "filename and root_cell must both be non-empty, and this experiment must have an uploaded file."}]}
    file_path = updir / filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}

    file_format = classify_upload(file_path)
    if file_format == "10x_h5_matrix":
        input_path, input_type = file_path, "h5"
    elif file_format == "10x_mtx_bundle":
        try:
            input_path = extract_bundle(file_path)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Could not extract {filename!r}: {exc}"}]}
        input_type = "mtx_dir"
    else:
        return {"content": [{"type": "text", "text": f"{filename!r} was detected as format `{file_format}`, not a 10x-format matrix."}]}

    out_path = updir / f"{filename}.monocle_pseudotime.csv"
    code, out, err = await asyncio.to_thread(_run_monocle, input_path, input_type, root_cell, out_path)
    result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"Monocle3 pseudotime failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": "Monocle3 ran but produced no cells."}]}

    rows_sorted = sorted(rows, key=lambda r: float(r.get("pseudotime", "inf") or "inf"))
    lines = [f"Monocle3 pseudotime trajectory for {filename} rooted at {root_cell} [monocle:cell] -- {len(rows)} real cell(s):"]
    for row in rows_sorted[:MAX_ROWS_RETURNED]:
        lines.append(f"- {row.get('cell', '?')}: cluster={row.get('cluster', '?')}, pseudotime={row.get('pseudotime', '?')}")
    if len(rows) > MAX_ROWS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_ROWS_RETURNED} more cell(s) not shown (sorted by ascending pseudotime).")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_monocle_pseudotime_mcp_server():
    return create_sdk_mcp_server(name="monocle_pseudotime", tools=[monocle_pseudotime_trajectory])
