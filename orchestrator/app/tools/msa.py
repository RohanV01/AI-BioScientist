"""A real multiple-sequence-alignment MCP tool (docs/12-biotools-triage-
shortlist.md's Phylogenetics/Sequence-analysis clusters), wrapping the
real `mafft` CLI via subprocess against tempfiles -- same pattern as
app/tools/phylogenetics.py's PhyKIT wrapper and
literature_discovery.py's grep subprocess.

Real gap found by battle-testing every pipeline with hard, adversarial
questions (docs/15-battle-test-report.md, Battle 7): given two real,
naturally indel-bearing NCBI sequences (not hand-crafted to already be
aligned), phylogenetics.build_phylogenetic_tree -- which requires
pre-aligned, same-length input and has no way to align anything itself --
silently produced a corrupted tree (one taxon's branch length inflated to
the model's saturation ceiling) instead of erroring, because the raw
sequences were fed to it position-by-position with no alignment step in
between. The agent caught this itself through careful cross-checking
against an alignment-free method, but a researcher without that same
scrutiny would have taken the corrupted tree at face value. This tool
closes that gap: given raw, unaligned, possibly different-length
sequences, it produces a real MAFFT alignment whose output is directly
usable as build_phylogenetic_tree's input.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_mafft(input_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["mafft", "--quiet", "--auto", str(input_path)],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_fasta(text: str) -> dict[str, str]:
    sequences: dict[str, str] = {}
    name = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                sequences[name] = "".join(chunks)
            name = line[1:].strip()
            chunks = []
        elif name is not None:
            chunks.append(line.strip())
    if name is not None:
        sequences[name] = "".join(chunks)
    return sequences


@tool(
    "align_sequences",
    "Given a dict of {sequence_name: raw_sequence} (DNA or protein, "
    "NOT required to be the same length or pre-aligned -- that's the "
    "point of this tool), run a real multiple sequence alignment via "
    "MAFFT and return the aligned sequences (now all the same length, "
    "with '-' gap characters inserted). The result is directly usable as "
    "phylogenetics.build_phylogenetic_tree's `sequences` input -- always "
    "align real, independently-obtained sequences with this tool before "
    "tree-building; feeding unaligned sequences with real indels between "
    "them to the tree builder silently produces a corrupted tree, not an "
    "error. Never state an aligned sequence or gap position this tool "
    "didn't actually return.",
    {"sequences": dict},
)
async def align_sequences(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or len(sequences) < 2:
        return {"content": [{"type": "text", "text": "sequences must be a dict of at least 2 {name: sequence} pairs."}]}
    empty = [name for name, seq in sequences.items() if not seq]
    if empty:
        return {"content": [{"type": "text", "text": f"Empty sequence(s) for: {', '.join(empty)}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.fasta"
        input_path.write_text(
            "\n".join(f">{name}\n{seq}" for name, seq in sequences.items()) + "\n"
        )
        code, out, err = await asyncio.to_thread(_run_mafft, input_path)

    if code != 0 or not out.strip():
        return {"content": [{"type": "text", "text": f"MAFFT alignment failed: {err.strip() or 'no output produced'}"}]}

    aligned = _parse_fasta(out)
    lengths = {len(v) for v in aligned.values()}
    if len(lengths) != 1:
        # Shouldn't happen with a successful MAFFT run -- surfaced rather
        # than silently returning malformed output a caller might trust.
        return {"content": [{"type": "text", "text": f"MAFFT output sequences aren't uniform length ({sorted(lengths)}) -- alignment may have failed silently."}]}
    aligned_length = lengths.pop()

    # [mafft:alignment] is the citable unit -- real local computation, same
    # methodological-citation convention as scikit-bio/cobra/vina/piqtree.
    lines = [
        f"MAFFT alignment of {len(aligned)} sequences, aligned length {aligned_length}bp/aa "
        f"[mafft:alignment]:",
    ]
    for name, seq in aligned.items():
        gap_count = seq.count("-")
        lines.append(f"- {name} ({gap_count} gap positions): {seq}")
    lines.append(
        "\nUse these aligned sequences (as a {name: sequence} dict, unchanged) directly as "
        "phylogenetics.build_phylogenetic_tree's `sequences` argument."
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_msa_mcp_server():
    return create_sdk_mcp_server(name="msa", tools=[align_sequences])
