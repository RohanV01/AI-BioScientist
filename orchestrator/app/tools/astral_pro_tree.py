"""A real ASTRAL-Pro MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Phylogenetics cluster) -- subprocess-wrapped `astral-pro`
binary, compiled from source at Docker build time from the ASTER
project (github.com/chaoszhang/ASTER, the current real home of
ASTRAL-Pro -- see Dockerfile comment). Real species-tree estimation
from a set of unrooted gene-family trees, statistically consistent
under the multi-species coalescent model even with multi-copy genes
(paralogs) -- a job neither `phylogenetics.build_phylogenetic_tree`
(one tree from one alignment) nor FastTree covers.

Note: docs/17 named this cluster's tool "ASTRAL-Pro2" -- the ASTER
project has since moved to ASTRAL-Pro3, a faster reimplementation of
the same method (confirmed via its own README/tutorial before
building); wired as `astral-pro` (ASTER's own binary name) rather than
chasing an old version number.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# Confirmed against ASTER's own tutorial/astral-pro3.md: stderr reports
# quartet support as "Final quartet score is: <int>" and normalized
# score as "Final normalized quartet score is: <float>".
QUARTET_SCORE = re.compile(r"Final quartet score(?:\s*/\s*\d+)? is:\s*([\d.]+)")
NORMALIZED_SCORE = re.compile(r"Final normalized quartet score is:\s*([\d.]+)")


def _run_astral_pro(input_path: Path, output_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["astral-pro", "-i", str(input_path), "-o", str(output_path)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "build_species_tree",
    "Given a list of Newick gene-tree strings (each tree is one gene "
    "family across multiple species; leaf names encode "
    "species/gene identity, and can repeat across trees for multi-copy "
    "genes/paralogs), infer a real species tree via ASTRAL-Pro -- "
    "statistically consistent under the multi-species coalescent model, "
    "the standard way to reconcile many gene trees (which can "
    "individually disagree due to incomplete lineage sorting or gene "
    "duplication) into one species tree. Never state a species-tree "
    "topology, branch length, or quartet score this tool didn't "
    "actually compute.",
    {"gene_trees": list},
)
async def build_species_tree(args: dict[str, Any]) -> dict[str, Any]:
    gene_trees = args.get("gene_trees")
    if not isinstance(gene_trees, list) or len(gene_trees) < 2:
        return {"content": [{"type": "text", "text": "gene_trees must be a list of at least 2 Newick tree strings."}]}
    gene_trees = [t.strip() for t in gene_trees if isinstance(t, str) and t.strip()]
    if len(gene_trees) < 2:
        return {"content": [{"type": "text", "text": "gene_trees must contain at least 2 non-empty Newick strings."}]}
    for t in gene_trees:
        if not t.endswith(";"):
            return {"content": [{"type": "text", "text": f"each gene tree must be a valid Newick string ending in ';' -- got: {t[:80]}"}]}

    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "gene_trees.nwk"
        input_path.write_text("\n".join(gene_trees) + "\n")
        output_path = Path(tmp) / "species_tree.nwk"

        code, out, err = await asyncio.to_thread(_run_astral_pro, input_path, output_path)
        newick = output_path.read_text().strip() if output_path.exists() else ""

    if code != 0 or not newick:
        return {"content": [{"type": "text", "text": f"ASTRAL-Pro failed: {err.strip() or out.strip() or 'no species tree produced'}"}]}

    lines = [f"ASTRAL-Pro species tree from {len(gene_trees)} gene trees [astral_pro:tree]:", newick]
    quartet_match = QUARTET_SCORE.search(err)
    normalized_match = NORMALIZED_SCORE.search(err)
    if quartet_match:
        lines.append(f"Final quartet score: {quartet_match.group(1)}")
    if normalized_match:
        lines.append(f"Normalized quartet score: {normalized_match.group(1)}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_astral_pro_tree_mcp_server():
    return create_sdk_mcp_server(name="astral_pro_tree", tools=[build_species_tree])
