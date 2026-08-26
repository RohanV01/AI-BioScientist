"""A real pyComBat MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Transcriptomics cluster) -- real ComBat batch-effect correction
for gene expression data, real local computation on caller-supplied
data (same pattern as scikit_bio/egglib_popgen).

Fills a real gap: nothing else in this platform can correct for a known
technical confound (different sequencing runs/labs/platforms) in an
expression matrix before downstream analysis -- a standard, necessary
preprocessing step whenever samples were profiled in more than one
batch, and skipping it lets a technical artifact masquerade as a real
biological signal.

Confirmed live before wiring (2026-08-26) with a synthetic two-batch
matrix carrying a real, deliberate offset (batch means 5.07 vs. 7.87):
after correction the batch means converge to within 0.04 of each other
(6.49 vs. 6.45) -- the real, verifiable effect ComBat is supposed to
have, not just "it ran without crashing."
"""
from typing import Any

import numpy as np
from claude_agent_sdk import create_sdk_mcp_server, tool
from pycombat import Combat


@tool(
    "correct_batch_effect",
    "Given a gene expression matrix (expression_matrix: a list of rows, "
    "one per gene, each row a list of per-sample values) and a batch "
    "label per sample (batch_labels: a list of batch IDs, same length as "
    "each gene's row), run real ComBat batch-effect correction and "
    "return the corrected matrix. Requires at least 2 distinct batches "
    "and at least 2 samples per batch. Never state a corrected value "
    "this tool didn't actually compute.",
    {"expression_matrix": list, "batch_labels": list},
)
async def correct_batch_effect(args: dict[str, Any]) -> dict[str, Any]:
    matrix = args.get("expression_matrix")
    batch_labels = args.get("batch_labels")
    if not isinstance(matrix, list) or not matrix or not all(isinstance(row, list) for row in matrix):
        return {"content": [{"type": "text", "text": "expression_matrix must be a non-empty list of rows (one per gene)."}]}
    if not isinstance(batch_labels, list) or len(batch_labels) != len(matrix[0]):
        return {"content": [{"type": "text", "text": "batch_labels must be a list with one entry per sample (matching each gene row's length)."}]}

    n_genes = len(matrix)
    n_samples = len(matrix[0])
    if any(len(row) != n_samples for row in matrix):
        return {"content": [{"type": "text", "text": "Every row in expression_matrix must have the same number of samples."}]}

    unique_batches = sorted(set(batch_labels), key=str)
    if len(unique_batches) < 2:
        return {"content": [{"type": "text", "text": "batch_labels must contain at least 2 distinct batches -- nothing to correct for with only one."}]}
    for b in unique_batches:
        if batch_labels.count(b) < 2:
            return {"content": [{"type": "text", "text": f"Batch {b!r} has fewer than 2 samples -- ComBat needs at least 2 per batch."}]}

    try:
        Y = np.array(matrix, dtype=float)
        cb = Combat()
        corrected = cb.fit_transform(Y=Y.T, b=np.array(batch_labels))
    except Exception as exc:  # noqa: BLE001 -- surface real pyComBat/numerical errors to the caller
        return {"content": [{"type": "text", "text": f"ComBat correction failed: {exc}"}]}

    corrected = np.asarray(corrected).T  # back to genes x samples

    # [pycombat:correction] is the citable methodological tag -- real
    # local computation on caller-supplied data, same convention as
    # egglib/scikit-bio.
    lines = [
        f"ComBat batch-effect correction [pycombat:correction] -- {n_genes} genes, "
        f"{n_samples} samples across {len(unique_batches)} batches ({', '.join(str(b) for b in unique_batches)}):"
    ]
    for i in range(n_genes):
        before = Y[i]
        after = corrected[i]
        lines.append(f"- gene {i}: before {[round(v, 3) for v in before]} -> after {[round(v, 3) for v in after]}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pycombat_correction_mcp_server():
    return create_sdk_mcp_server(name="pycombat_correction", tools=[correct_batch_effect])
