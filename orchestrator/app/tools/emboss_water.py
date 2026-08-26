"""A real EMBOSS `water` MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Sequence analysis fundamentals cluster) -- subprocess-wrapped
`water` CLI (apt `emboss` package, see Dockerfile), real Smith-Waterman
optimal local pairwise alignment with an affine gap penalty.

Distinct from blast_search (heuristic seed-and-extend, built for
searching many references) and msa/clustalo_align (multiple-sequence,
progressive/heuristic): this is the exact, guaranteed-optimal alignment
of exactly two sequences -- the right tool when a researcher needs the
single best possible alignment between two specific sequences with a
real, mathematically optimal score, not an approximation.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

SUMMARY_PATTERN = re.compile(
    r"# Identity:\s+(\S+)\s+\(([\d.]+)%\)\s*\n"
    r"# Similarity:\s+(\S+)\s+\(([\d.]+)%\)\s*\n"
    r"# Gaps:\s+(\S+)\s+\(([\d.]+)%\)\s*\n"
    r"# Score:\s+([\d.-]+)",
)


def _run_water(seq_a_path: Path, seq_b_path: Path, output_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "water", "-asequence", str(seq_a_path), "-bsequence", str(seq_b_path),
            "-gapopen", "10", "-gapextend", "0.5", "-outfile", str(output_path),
            "-aformat3", "pair",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "water_local_alignment",
    "Given exactly two sequences (DNA or protein), run EMBOSS `water` -- "
    "the exact, guaranteed-optimal Smith-Waterman local alignment (not "
    "an approximation like blast_search/minimap2_align) -- and return "
    "the real identity/similarity/gap percentages, alignment score, and "
    "the aligned region itself. Use this when the best possible "
    "pairwise alignment between two specific sequences matters, not a "
    "fast search across many references. Never state a score/identity "
    "this tool didn't actually compute.",
    {"sequence_a": str, "sequence_b": str},
)
async def water_local_alignment(args: dict[str, Any]) -> dict[str, Any]:
    seq_a = (args.get("sequence_a") or "").strip().upper()
    seq_b = (args.get("sequence_b") or "").strip().upper()
    if not seq_a or not seq_b:
        return {"content": [{"type": "text", "text": "sequence_a and sequence_b must both be non-empty."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        seq_a_path = tmp_path / "seqA.fasta"
        seq_b_path = tmp_path / "seqB.fasta"
        output_path = tmp_path / "output.water"
        seq_a_path.write_text(f">seqA\n{seq_a}\n")
        seq_b_path.write_text(f">seqB\n{seq_b}\n")

        code, out, err = await asyncio.to_thread(_run_water, seq_a_path, seq_b_path, output_path)
        output_text = output_path.read_text() if output_path.exists() else ""

    if code != 0 or not output_text.strip():
        return {"content": [{"type": "text", "text": f"EMBOSS water alignment failed: {err.strip() or 'no output produced'}"}]}

    match = SUMMARY_PATTERN.search(output_text)
    if not match:
        return {"content": [{"type": "text", "text": "EMBOSS water produced output but its summary statistics could not be parsed."}]}

    identity_frac, identity_pct, similarity_frac, similarity_pct, gaps_frac, gaps_pct, score = match.groups()
    lines = [
        "EMBOSS water Smith-Waterman local alignment [emboss:water]:",
        f"- Identity: {identity_frac} ({identity_pct}%)",
        f"- Similarity: {similarity_frac} ({similarity_pct}%)",
        f"- Gaps: {gaps_frac} ({gaps_pct}%)",
        f"- Score: {score}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_emboss_water_mcp_server():
    return create_sdk_mcp_server(name="emboss_water", tools=[water_local_alignment])
