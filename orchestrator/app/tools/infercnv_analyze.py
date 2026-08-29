"""A real InferCNV MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript`
running InferCNV's own canonical workflow (CreateInfercnvObject ->
run), same pattern as `seurat_analyze`. Gene chromosomal positions are
fetched live from Ensembl (via biomaRt, inside the R script) for
exactly the genes in the uploaded matrix, every run -- no baked-in
gene-order reference snapshot. Cell group labels (e.g. tumor vs.
reference/normal) must come from a second real uploaded annotations
table, never fabricated.
"""
import asyncio
import csv
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.experiment_context import uploads_dir
from app.file_uploads import classify_upload, extract_bundle

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "infercnv_analyze.R")
MAX_ROWS_RETURNED = 25


def _run_infercnv(input_path: Path, input_type: str, annotations_path: Path, ref_groups: str, out_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(input_path), input_type, str(annotations_path), ref_groups, str(out_dir)],
        capture_output=True, text=True, timeout=1800,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "infercnv_detect_cnv",
    "Given the filename of a real uploaded single-cell RNA-seq count "
    "matrix (see list_uploaded_files -- format `10x_h5_matrix` or "
    "`10x_mtx_bundle`), the filename of a real uploaded cell "
    "annotations table (a two-column TSV of cell barcode -> group "
    "label, uploaded as a `table`), and the exact group label(s) in "
    "that table representing normal/reference cells (comma-separated "
    "if more than one), run InferCNV to detect copy-number variation "
    "signal per cell relative to those reference cells. Gene "
    "chromosomal positions are looked up live from Ensembl -- never "
    "invent a chromosome position or CNV signal this tool didn't "
    "actually compute. Genuinely slow -- do not abandon a call early "
    "on this basis alone.",
    {"filename": str, "annotations_filename": str, "ref_group_names": str},
)
async def infercnv_detect_cnv(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    annotations_filename = (args.get("annotations_filename") or "").strip()
    ref_group_names = (args.get("ref_group_names") or "").strip()
    updir = uploads_dir()
    if not filename or not annotations_filename or not ref_group_names or updir is None:
        return {"content": [{"type": "text", "text": "filename, annotations_filename, and ref_group_names must all be non-empty, and this experiment must have uploaded files."}]}

    file_path = updir / filename
    annotations_path = updir / annotations_filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}
    if not annotations_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {annotations_filename!r} in this experiment -- call list_uploaded_files first."}]}

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

    out_dir = updir / f"{filename}.infercnv_out"
    code, out, err = await asyncio.to_thread(_run_infercnv, input_path, input_type, annotations_path, ref_group_names, out_dir)

    obs_path = out_dir / "infercnv.observations.txt"
    if code != 0 or not obs_path.exists():
        return {"content": [{"type": "text", "text": f"InferCNV failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    # infercnv.observations.txt: rows=genes, columns=cells, values are
    # smoothed relative expression centered on 1.0 -- real per-cell
    # CNV burden proxy is the mean absolute deviation from 1.0 across
    # genes, ranked descending.
    with obs_path.open() as fh:
        reader = csv.reader(fh, delimiter=" ")
        header = next(reader)
        cell_ids = [c.strip('"') for c in header]
        sums = [0.0] * len(cell_ids)
        n_genes = 0
        for row in reader:
            values = row[1:]
            if len(values) != len(cell_ids):
                continue
            n_genes += 1
            for i, v in enumerate(values):
                try:
                    sums[i] += abs(float(v) - 1.0)
                except ValueError:
                    pass

    if n_genes == 0:
        return {"content": [{"type": "text", "text": "InferCNV ran but produced no gene rows to summarize."}]}

    burden = sorted(zip(cell_ids, (s / n_genes for s in sums)), key=lambda kv: -kv[1])
    lines = [f"InferCNV analysis for {filename} [infercnv:cell] -- {len(cell_ids)} cell(s), {n_genes} gene(s), reference group(s): {ref_group_names}"]
    lines.append("Top cells by mean CNV deviation from reference baseline:")
    for cell, dev in burden[:MAX_ROWS_RETURNED]:
        lines.append(f"- {cell}: mean |deviation|={dev:.4f}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_infercnv_analyze_mcp_server():
    return create_sdk_mcp_server(name="infercnv_analyze", tools=[infercnv_detect_cnv])
