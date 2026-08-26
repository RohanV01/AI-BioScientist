"""A real Clustal Omega MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Sequence analysis fundamentals cluster) -- subprocess-wrapped
`clustalo` CLI (apt `clustalo` package, see Dockerfile), same pattern
as msa.py's MAFFT wrapper.

Distinct from the already-live `msa` (MAFFT) tool: this wires
Clustal Omega's `--distmat-out` percent-identity distance matrix
directly, a real second output MAFFT doesn't offer as a single CLI
flag -- useful for a quick "how similar are these sequences to each
other" screening pass without needing a separate distance computation
step. The alignment itself uses the same HMM-based progressive
algorithm many downstream bioinformatics tools (Pfam, InterPro) expect
as their reference alignment method.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_clustalo(input_path: Path, aligned_path: Path, distmat_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "clustalo", "-i", str(input_path), "-o", str(aligned_path),
            "--distmat-out", str(distmat_path), "--percent-id", "--full",
            "--outfmt=fasta", "--force",
        ],
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
    "align_sequences_clustalo",
    "Given a dict of {sequence_name: raw_sequence} (DNA or protein, not "
    "required to be pre-aligned), run a real Clustal Omega multiple "
    "sequence alignment and return both the aligned sequences and a "
    "pairwise percent-identity distance matrix -- a real second output "
    "the already-live 'align_sequences' (MAFFT) tool doesn't provide in "
    "one call. Never state an aligned sequence, gap position, or "
    "percent identity this tool didn't actually compute.",
    {"sequences": dict},
)
async def align_sequences_clustalo(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or len(sequences) < 2:
        return {"content": [{"type": "text", "text": "sequences must be a dict of at least 2 {name: sequence} pairs."}]}
    empty = [name for name, seq in sequences.items() if not seq]
    if empty:
        return {"content": [{"type": "text", "text": f"Empty sequence(s) for: {', '.join(empty)}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text("\n".join(f">{name}\n{seq}" for name, seq in sequences.items()) + "\n")
        aligned_path = tmp_path / "aligned.fasta"
        distmat_path = tmp_path / "distmat.txt"

        code, out, err = await asyncio.to_thread(_run_clustalo, input_path, aligned_path, distmat_path)
        aligned_text = aligned_path.read_text() if aligned_path.exists() else ""
        distmat_text = distmat_path.read_text() if distmat_path.exists() else ""

    if code != 0 or not aligned_text.strip():
        return {"content": [{"type": "text", "text": f"Clustal Omega alignment failed: {err.strip() or 'no output produced'}"}]}

    aligned = _parse_fasta(aligned_text)
    lines = [f"Clustal Omega alignment of {len(aligned)} sequences [clustalo:alignment]:"]
    for name, seq in aligned.items():
        gap_count = seq.count("-")
        lines.append(f"- {name} ({gap_count} gap positions): {seq}")

    if distmat_text.strip():
        lines.append("\nPairwise percent identity distance matrix:")
        lines.extend(distmat_text.strip().splitlines()[1:])  # skip clustalo's leading count-only header line

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_clustalo_align_mcp_server():
    return create_sdk_mcp_server(name="clustalo_align", tools=[align_sequences_clustalo])
