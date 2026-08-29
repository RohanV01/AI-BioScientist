"""A real Seurat MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript` running
Seurat's own canonical scRNA-seq tutorial pipeline verbatim
(Read10X[_h5] -> CreateSeuratObject -> NormalizeData ->
FindVariableFeatures -> ScaleData -> RunPCA -> FindNeighbors ->
FindClusters -> FindAllMarkers), same pattern as
`cluster_profiler_enrichment`. Real single-cell clustering and marker-
gene detection from a researcher's own uploaded count matrix (a
CellRanger `.h5`/`.h5ad` file, or a zipped 10x matrix.mtx/barcodes.tsv/
features.tsv bundle -- see `list_uploaded_files`).

Requires a real uploaded file -- never accepts inline expression data
as a substitute; a real scRNA-seq matrix (thousands of cells) is not
something a chat message can reasonably carry inline the way
`wgcna_modules`'s much smaller caller-supplied matrix can.
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

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "seurat_analyze.R")
MAX_ROWS_RETURNED = 20


def _run_seurat(input_path: Path, input_type: str, clusters_out: Path, markers_out: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(input_path), input_type, str(clusters_out), str(markers_out)],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "seurat_analyze_scrna",
    "Given the filename of a real uploaded single-cell RNA-seq count "
    "matrix (see list_uploaded_files -- must have format "
    "`10x_h5_matrix` or `10x_mtx_bundle`), run Seurat's full clustering "
    "pipeline (normalize, PCA, neighbor graph, Leiden/Louvain "
    "clustering) and report each cluster's real size and top marker "
    "genes. Genuinely slow for a real dataset (thousands of cells) -- "
    "do not abandon a call early on this basis alone. Never state a "
    "cluster assignment or marker gene this tool didn't actually "
    "compute.",
    {"filename": str},
)
async def seurat_analyze_scrna(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    updir = uploads_dir()
    if not filename or updir is None:
        return {"content": [{"type": "text", "text": "filename must be non-empty, and this experiment must have an uploaded file."}]}
    file_path = updir / filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}

    file_format = classify_upload(file_path)
    if file_format == "10x_h5_matrix":
        input_path, input_type = file_path, "h5"
    elif file_format == "10x_mtx_bundle":
        try:
            input_path = extract_bundle(file_path)
        except (ValueError, Exception) as exc:  # noqa: BLE001 -- surface real archive-extraction errors to the caller
            return {"content": [{"type": "text", "text": f"Could not extract {filename!r}: {exc}"}]}
        input_type = "mtx_dir"
    else:
        return {"content": [{"type": "text", "text": f"{filename!r} was detected as format `{file_format}`, not a 10x-format matrix (h5/h5ad/loom or a matrix.mtx+barcodes.tsv+features.tsv bundle)."}]}

    clusters_out = updir / f"{filename}.seurat_clusters.csv"
    markers_out = updir / f"{filename}.seurat_markers.csv"
    code, out, err = await asyncio.to_thread(_run_seurat, input_path, input_type, clusters_out, markers_out)
    clusters_text = clusters_out.read_text() if clusters_out.exists() else ""
    markers_text = markers_out.read_text() if markers_out.exists() else ""

    if code != 0 or not clusters_text.strip():
        return {"content": [{"type": "text", "text": f"Seurat analysis failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    cluster_rows = list(csv.DictReader(io.StringIO(clusters_text)))
    cluster_counts: dict[str, int] = {}
    for row in cluster_rows:
        cluster_counts[row["cluster"]] = cluster_counts.get(row["cluster"], 0) + 1

    marker_rows = list(csv.DictReader(io.StringIO(markers_text))) if markers_text.strip() else []
    markers_by_cluster: dict[str, list[str]] = {}
    for row in marker_rows:
        markers_by_cluster.setdefault(row.get("cluster", "?"), []).append(row.get("gene", "?"))

    lines = [f"Seurat scRNA-seq clustering for {filename} [seurat:cluster] -- {len(cluster_counts)} cluster(s), {len(cluster_rows)} cell(s):"]
    for cluster_id, count in sorted(cluster_counts.items(), key=lambda kv: -kv[1])[:MAX_ROWS_RETURNED]:
        top_markers = markers_by_cluster.get(cluster_id, [])[:5]
        lines.append(f"- cluster {cluster_id}: {count} cells, top markers: {', '.join(top_markers) if top_markers else 'none passed threshold'}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_seurat_analyze_mcp_server():
    return create_sdk_mcp_server(name="seurat_analyze", tools=[seurat_analyze_scrna])
