"""A real Scanpy MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Transcriptomics cluster) -- the field-standard Python scRNA-seq
pipeline (QC metrics, normalization, PCA, neighbor graph, Leiden
clustering) on a caller-supplied count matrix.

**DATA-gated in practice, wired anyway per docs/17's explicit call**:
this is a real, complete computation -- not a stub -- but its practical
usefulness is capped until this platform has an actual scRNA-seq-matrix
upload/ingestion story (nothing here parses a real 10x/H5AD file today).
Wiring it now means the moment that ingestion story exists, this tool is
already real and tested, not a to-do.

Confirmed live before wiring (2026-08-26) two real API gotchas on a
small test matrix: `calculate_qc_metrics`'s default `percent_top`
requires more genes than a small/synthetic matrix has (needs
`percent_top=None` for anything under ~500 genes), and `tl.leiden`
needs the `igraph`+`leidenalg` packages installed separately (scanpy's
own error message names them, but they're not a transitive dependency).
"""
from typing import Any

import anndata as ad
import numpy as np
import scanpy as sc
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "cluster_expression_matrix",
    "Given a single-cell (or bulk) gene expression count matrix "
    "(expression_matrix: a list of rows, one per cell, each row a list "
    "of per-gene counts) and optional gene_names/cell_names, run the "
    "real Scanpy pipeline: QC metrics, total-count normalization, log "
    "transform, PCA, neighbor graph, and Leiden clustering. Returns "
    "each cell's cluster assignment and QC summary stats (genes "
    "detected, total counts). Requires at least 10 cells. Never state a "
    "cluster/statistic this tool didn't actually compute.",
    {"expression_matrix": list, "gene_names": list, "cell_names": list},
)
async def cluster_expression_matrix(args: dict[str, Any]) -> dict[str, Any]:
    matrix = args.get("expression_matrix")
    if not isinstance(matrix, list) or len(matrix) < 10 or not all(isinstance(row, list) for row in matrix):
        return {"content": [{"type": "text", "text": "expression_matrix must be a list of at least 10 cell rows."}]}
    n_genes = len(matrix[0])
    if n_genes < 3 or any(len(row) != n_genes for row in matrix):
        return {"content": [{"type": "text", "text": "Every cell row must have the same number of genes (at least 3)."}]}

    gene_names = args.get("gene_names") or [f"gene{i}" for i in range(n_genes)]
    cell_names = args.get("cell_names") or [f"cell{i}" for i in range(len(matrix))]
    if len(gene_names) != n_genes or len(cell_names) != len(matrix):
        return {"content": [{"type": "text", "text": "gene_names/cell_names, if given, must match the matrix dimensions."}]}

    import asyncio

    def _run():
        X = np.array(matrix, dtype=float)
        adata = ad.AnnData(X)
        adata.var_names = [str(g) for g in gene_names]
        adata.obs_names = [str(c) for c in cell_names]
        sc.pp.calculate_qc_metrics(adata, inplace=True, percent_top=None)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        n_comps = min(10, min(adata.shape) - 1)
        if n_comps < 2:
            raise ValueError("Matrix too small for PCA -- need more cells/genes.")
        sc.pp.pca(adata, n_comps=n_comps)
        n_neighbors = min(15, len(matrix) - 1)
        sc.pp.neighbors(adata, n_neighbors=n_neighbors)
        sc.tl.leiden(adata, flavor="igraph", n_iterations=2)
        return adata

    try:
        adata = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001 -- surface real Scanpy/numerical errors to the caller
        return {"content": [{"type": "text", "text": f"Scanpy clustering failed: {exc}"}]}

    n_clusters = adata.obs["leiden"].nunique()
    # [scanpy:leiden] is the citable methodological tag -- real local
    # computation on caller-supplied data, same convention as egglib.
    lines = [
        f"Scanpy clustering [scanpy:leiden] -- {len(matrix)} cells, {n_genes} genes, "
        f"{n_clusters} Leiden cluster(s) found:"
    ]
    for cell, cluster, n_genes_detected, total_counts in zip(
        adata.obs_names, adata.obs["leiden"], adata.obs["n_genes_by_counts"], adata.obs["total_counts"]
    ):
        lines.append(f"- {cell}: cluster {cluster} ({int(n_genes_detected)} genes detected, {total_counts:.0f} total counts)")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_scanpy_clustering_mcp_server():
    return create_sdk_mcp_server(name="scanpy_clustering", tools=[cluster_expression_matrix])
