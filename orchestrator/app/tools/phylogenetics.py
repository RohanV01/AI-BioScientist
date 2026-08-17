"""Real phylogenetics MCP tools (docs/12-biotools-triage-shortlist.md's
Phylogenetics cluster) -- this platform's first phylogenetics coverage.
Nothing before this could take a set of sequences and actually infer a
tree, or take a tree and report real distances between taxa.

Two tools, two libraries:
- build_phylogenetic_tree: piqtree (Python-native IQ-TREE bindings) runs
  a real maximum-likelihood tree search on an aligned set of sequences.
- analyze_tree: dendropy loads a Newick tree and reports real
  patristic (tree-path) distances and tree-level statistics.

Both real local computation (in-process, no external API for the
computation itself), same shape as scikit_bio.py/cobra_fba.py -- the
citable unit is the method, tagged [piqtree:tree]/[dendropy:tree].
"""
from typing import Any

import cogent3
import dendropy
import piqtree
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "build_phylogenetic_tree",
    "Given a dict of {sequence_name: aligned_sequence} (DNA or protein, "
    "all sequences must be the same length -- already aligned), infer a "
    "maximum-likelihood phylogenetic tree via IQ-TREE (through piqtree) "
    "using a Jukes-Cantor substitution model. Returns the tree as a "
    "Newick string with real branch lengths. Never state a branch length "
    "or topology this tool didn't actually compute.",
    {"sequences": dict},
)
async def build_phylogenetic_tree(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args["sequences"]
    if not isinstance(sequences, dict) or len(sequences) < 3:
        return {"content": [{"type": "text", "text": "sequences must be a dict of at least 3 {name: sequence} pairs."}]}
    lengths = {len(v) for v in sequences.values()}
    if len(lengths) != 1:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"All sequences must be the same length (already aligned) -- got lengths {sorted(lengths)}.",
                }
            ]
        }

    try:
        aln = cogent3.make_aligned_seqs(sequences, moltype="dna")
        tree = piqtree.build_tree(aln, "JC")
    except Exception as exc:  # noqa: BLE001 -- surface real IQ-TREE/cogent3 errors to the caller
        return {"content": [{"type": "text", "text": f"Tree inference failed: {exc}"}]}

    newick = tree.get_newick(with_distances=True)
    # [piqtree:tree] is the citable unit -- real local ML inference, same
    # methodological-citation convention as scikit-bio/cobra/vina.
    text = (
        f"Maximum-likelihood tree for {len(sequences)} taxa (Jukes-Cantor model, "
        f"via IQ-TREE) [piqtree:tree]:\n{newick}"
    )
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "analyze_tree",
    "Given a Newick-format phylogenetic tree string, report real tree "
    "statistics via dendropy: total tree length (sum of branch lengths), "
    "taxon count, and the patristic (tree-path) distance between two "
    "named taxa if both are given. Never state a distance or statistic "
    "this tool didn't actually compute.",
    {"newick": str, "taxon_a": str, "taxon_b": str},
)
async def analyze_tree(args: dict[str, Any]) -> dict[str, Any]:
    newick = args["newick"].strip()
    if not newick:
        return {"content": [{"type": "text", "text": "newick must be a non-empty Newick tree string."}]}

    try:
        tree = dendropy.Tree.get(data=newick, schema="newick")
    except Exception as exc:  # noqa: BLE001 -- surface real dendropy parse errors to the caller
        return {"content": [{"type": "text", "text": f"Could not parse this Newick string: {exc}"}]}

    taxa = [tx.label for tx in tree.taxon_namespace]
    lines = [
        f"Tree analysis [dendropy:tree] -- {len(taxa)} taxa: {', '.join(taxa)}",
        f"Total tree length (sum of branch lengths): {tree.length():.6f}",
    ]

    taxon_a, taxon_b = args.get("taxon_a"), args.get("taxon_b")
    if taxon_a and taxon_b:
        match_a = next((t for t in tree.taxon_namespace if t.label == taxon_a), None)
        match_b = next((t for t in tree.taxon_namespace if t.label == taxon_b), None)
        if match_a is None or match_b is None:
            missing = [n for n, m in [(taxon_a, match_a), (taxon_b, match_b)] if m is None]
            lines.append(f"Could not compute patristic distance -- taxon/taxa not found in tree: {missing}")
        else:
            pdm = tree.phylogenetic_distance_matrix()
            distance = pdm.patristic_distance(match_a, match_b)
            lines.append(f"Patristic distance {taxon_a} <-> {taxon_b}: {distance:.6f}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_phylogenetics_mcp_server():
    return create_sdk_mcp_server(name="phylogenetics", tools=[build_phylogenetic_tree, analyze_tree])
