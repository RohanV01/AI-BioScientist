"""A real FastTree MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Phylogenetics cluster) -- subprocess-wrapped `fasttree` CLI
(apt `fasttree` package, see Dockerfile), real approximate-maximum-
likelihood tree inference from an aligned set of sequences.

Distinct from the existing `phylogenetics.build_phylogenetic_tree`
(piqtree/IQ-TREE): FastTree trades some accuracy for speed on much
larger alignments (hundreds-thousands of sequences) via a
neighbor-joining + minimum-evolution + ML-refinement heuristic, the
real reason to reach for it over IQ-TREE for a big alignment rather
than duplicating the same job.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_fasttree(input_path: Path, is_nucleotide: bool) -> tuple[int, str, str]:
    # -nt: nucleotide model (GTR); omitted = protein model (JTT), FastTree's
    # own default -- real flag, not guessed, confirmed against FastTree's
    # own -help text.
    cmd = ["fasttree"]
    if is_nucleotide:
        cmd.append("-nt")
    cmd.append(str(input_path))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "build_fasttree",
    "Given a dict of {sequence_name: aligned_sequence} (DNA or protein, "
    "all sequences must already be the same length -- aligned), infer an "
    "approximate maximum-likelihood phylogenetic tree via FastTree. Faster "
    "than IQ-TREE-based tree building for larger alignments (dozens to "
    "thousands of taxa), at some cost in accuracy. Returns a Newick tree "
    "with real branch lengths. Never state a branch length or topology "
    "this tool didn't actually compute.",
    {"sequences": dict, "is_nucleotide": bool},
)
async def build_fasttree(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or len(sequences) < 3:
        return {"content": [{"type": "text", "text": "sequences must be a dict of at least 3 {name: sequence} pairs."}]}
    lengths = {len(v) for v in sequences.values()}
    if len(lengths) != 1:
        return {
            "content": [
                {"type": "text", "text": f"All sequences must be the same length (already aligned) -- got lengths {sorted(lengths)}."}
            ]
        }
    is_nucleotide = bool(args.get("is_nucleotide", True))

    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.fasta"
        input_path.write_text("".join(f">{name}\n{seq}\n" for name, seq in sequences.items()))
        code, out, err = await asyncio.to_thread(_run_fasttree, input_path, is_nucleotide)

    if code != 0 or not out.strip():
        return {"content": [{"type": "text", "text": f"FastTree failed: {err.strip() or 'no tree produced'}"}]}

    newick = out.strip()
    model = "GTR" if is_nucleotide else "JTT"
    text = (
        f"FastTree approximate-ML tree for {len(sequences)} taxa ({model} model) "
        f"[fasttree:tree]:\n{newick}"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_fasttree_tree_mcp_server():
    return create_sdk_mcp_server(name="fasttree_tree", tools=[build_fasttree])
