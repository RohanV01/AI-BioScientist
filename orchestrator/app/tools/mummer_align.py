"""A real MUMmer4 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Sequence analysis fundamentals cluster) -- subprocess-wrapped
`nucmer` + `show-coords` CLI (apt `mummer` package, see Dockerfile),
real whole-genome/large-sequence nucleotide alignment.

Distinct from blast_search (many short references, statistical
significance) and minimap2_align (fast approximate long-read/cDNA
alignment): MUMmer's maximal-unique-match (MUM) anchoring algorithm is
built specifically for aligning two large, mostly-similar sequences
(e.g. two genome assemblies, or a genome against a close reference) to
find real structural correspondence -- matching blocks, their real
coordinates in both sequences, and percent identity -- not a search
across many candidates.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_MATCHES_RETURNED = 30


def _run_nucmer(ref_path: Path, query_path: Path, prefix: str, tmp: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["nucmer", "--prefix", prefix, str(ref_path), str(query_path)],
        capture_output=True, text=True, timeout=60, cwd=tmp,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_show_coords(delta_path: Path, tmp: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["show-coords", "-r", "-c", "-l", "-T", str(delta_path)],
        capture_output=True, text=True, timeout=30, cwd=tmp,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "mummer_align",
    "Given two large, mostly-similar nucleotide sequences (e.g. two "
    "genome assemblies, or a genome against a close reference), run "
    "real MUMmer4 (nucmer) whole-sequence alignment to find matching "
    "blocks -- real coordinates in both sequences, aligned length, and "
    "percent identity. Distinct from blast_search/minimap2_align "
    "(built for many short references): this is built for structural "
    "comparison of two large, related sequences. Never state a match "
    "coordinate/identity this tool didn't actually compute.",
    {"reference_sequence": str, "query_sequence": str, "max_results": int},
)
async def mummer_align(args: dict[str, Any]) -> dict[str, Any]:
    reference = (args.get("reference_sequence") or "").strip().upper()
    query = (args.get("query_sequence") or "").strip().upper()
    max_results = min(int(args.get("max_results", 10)), 30)

    if not reference or not query:
        return {"content": [{"type": "text", "text": "reference_sequence and query_sequence must both be non-empty."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ref_path = tmp_path / "ref.fasta"
        query_path = tmp_path / "query.fasta"
        ref_path.write_text(f">reference\n{reference}\n")
        query_path.write_text(f">query\n{query}\n")

        code, out, err = await asyncio.to_thread(_run_nucmer, ref_path, query_path, "out", tmp)
        if code != 0:
            return {"content": [{"type": "text", "text": f"nucmer alignment failed: {err.strip() or 'unknown error'}"}]}

        delta_path = tmp_path / "out.delta"
        if not delta_path.exists():
            return {"content": [{"type": "text", "text": "nucmer produced no alignment output."}]}

        code, out, err = await asyncio.to_thread(_run_show_coords, delta_path, tmp)

    if code != 0:
        return {"content": [{"type": "text", "text": f"show-coords failed: {err.strip() or 'unknown error'}"}]}

    data_lines = [l for l in out.strip().splitlines() if l and l[0].isdigit()]
    if not data_lines:
        return {"content": [{"type": "text", "text": "No aligned matching regions found between the two sequences."}]}

    lines = [f"MUMmer4 (nucmer) [mummer:nucmer] -- {len(data_lines)} matching region(s):"]
    for row in data_lines[:max_results]:
        parts = row.split("\t")
        if len(parts) < 7:
            continue
        s1, e1, s2, e2, len1, len2, pid = parts[:7]
        lines.append(f"- reference {s1}-{e1} vs query {s2}-{e2}: {len1}bp/{len2}bp aligned, {pid}% identity")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_mummer_align_mcp_server():
    return create_sdk_mcp_server(name="mummer_align", tools=[mummer_align])
