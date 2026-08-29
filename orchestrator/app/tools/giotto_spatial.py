"""A real Giotto MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript`
running Giotto's own canonical spatial-transcriptomics workflow
(createGiottoObject -> normalizeGiotto -> calculateHVF -> runPCA ->
createNearestNetwork -> doLeidenCluster -> findMarkers_one_vs_all),
same pattern as `seurat_analyze`. Requires a real uploaded spatial
coordinates table (spot/cell ID -> x,y) alongside the expression
matrix -- Giotto's spatial clustering has no meaning without real
coordinates.
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

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "giotto_spatial.R")
MAX_ROWS_RETURNED = 20


def _run_giotto(input_path: Path, input_type: str, spatial_locs: Path, clusters_out: Path, markers_out: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(input_path), input_type, str(spatial_locs), str(clusters_out), str(markers_out)],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "giotto_analyze_spatial",
    "Given the filename of a real uploaded spatial gene-expression "
    "count matrix (see list_uploaded_files -- format `10x_h5_matrix` "
    "or `10x_mtx_bundle`) and the filename of a real uploaded spatial "
    "coordinates table (a TSV with cell/spot ID as the first column "
    "and x,y coordinates as the next two, uploaded as a `table`), run "
    "Giotto to spatially cluster the data and find each cluster's "
    "marker genes. Never state a cluster or spatial pattern this tool "
    "didn't actually compute.",
    {"filename": str, "spatial_locs_filename": str},
)
async def giotto_analyze_spatial(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    spatial_locs_filename = (args.get("spatial_locs_filename") or "").strip()
    updir = uploads_dir()
    if not filename or not spatial_locs_filename or updir is None:
        return {"content": [{"type": "text", "text": "filename and spatial_locs_filename must both be non-empty, and this experiment must have uploaded files."}]}

    file_path = updir / filename
    spatial_locs_path = updir / spatial_locs_filename
    if not file_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}
    if not spatial_locs_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {spatial_locs_filename!r} in this experiment -- call list_uploaded_files first."}]}

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

    clusters_out = updir / f"{filename}.giotto_clusters.csv"
    markers_out = updir / f"{filename}.giotto_markers.csv"
    code, out, err = await asyncio.to_thread(_run_giotto, input_path, input_type, spatial_locs_path, clusters_out, markers_out)
    clusters_text = clusters_out.read_text() if clusters_out.exists() else ""
    markers_text = markers_out.read_text() if markers_out.exists() else ""

    if code != 0 or not clusters_text.strip():
        return {"content": [{"type": "text", "text": f"Giotto analysis failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    cluster_rows = list(csv.DictReader(io.StringIO(clusters_text)))
    cluster_counts: dict[str, int] = {}
    for row in cluster_rows:
        cluster_counts[row["cluster"]] = cluster_counts.get(row["cluster"], 0) + 1

    marker_rows = list(csv.DictReader(io.StringIO(markers_text))) if markers_text.strip() else []
    markers_by_cluster: dict[str, list[str]] = {}
    for row in marker_rows:
        markers_by_cluster.setdefault(row.get("cluster", "?"), []).append(row.get("gene", "?"))

    lines = [f"Giotto spatial analysis for {filename} [giotto:cluster] -- {len(cluster_counts)} spatial cluster(s), {len(cluster_rows)} spot(s)/cell(s):"]
    for cluster_id, count in sorted(cluster_counts.items(), key=lambda kv: -kv[1])[:MAX_ROWS_RETURNED]:
        top_markers = markers_by_cluster.get(cluster_id, [])[:5]
        lines.append(f"- cluster {cluster_id}: {count} spots, top markers: {', '.join(top_markers) if top_markers else 'none passed threshold'}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_giotto_spatial_mcp_server():
    return create_sdk_mcp_server(name="giotto_spatial", tools=[giotto_analyze_spatial])
