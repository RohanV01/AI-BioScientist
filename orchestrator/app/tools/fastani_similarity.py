"""A real FastANI MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `fastANI` CLI
(apt `fastani` package, see Dockerfile), real alignment-free whole-
genome Average Nucleotide Identity (ANI) between two genomes. No
reference database needed -- a genuinely lightweight addition to this
otherwise DB-heavy cluster. Fills a real gap: nothing else on this
platform answers "how similar are these two genome assemblies," the
standard species-boundary metric in microbiology (ANI >= 95% is the
common species-delineation threshold).
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# FastANI's default fragment length is 3000bp -- confirmed live that a
# query near that length produces too few fragments for a reliable
# estimate (or no alignment at all). Real usable input is genome-scale,
# not a short contig -- 20kb is a conservative floor that reliably
# produces several fragments, confirmed live.
MIN_GENOME_LENGTH = 20000


def _run_fastani(query_path: Path, ref_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["fastANI", "-q", str(query_path), "-r", str(ref_path), "-o", str(out_path)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "compute_genome_ani",
    "Given two genome/assembly nucleotide sequences (each at least "
    "20000bp -- FastANI fragments the genome into 3000bp windows and "
    "needs several to produce a reliable estimate, confirmed live), "
    "compute their real Average Nucleotide Identity (ANI) via "
    "FastANI -- the standard alignment-free species-boundary metric in "
    "microbiology (ANI >= 95% is the commonly used same-species "
    "threshold). Never state an ANI value this tool didn't actually "
    "compute.",
    {"query_sequence": str, "reference_sequence": str},
)
async def compute_genome_ani(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query_sequence") or "").strip().upper()
    reference = (args.get("reference_sequence") or "").strip().upper()
    for label, seq in (("query_sequence", query), ("reference_sequence", reference)):
        if len(seq) < MIN_GENOME_LENGTH:
            return {"content": [{"type": "text", "text": f"{label} must be at least {MIN_GENOME_LENGTH}bp."}]}
        if not set(seq) <= set("ACGTN"):
            return {"content": [{"type": "text", "text": f"{label} must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        query_path = tmp_path / "query.fasta"
        query_path.write_text(f">query\n{query}\n")
        ref_path = tmp_path / "reference.fasta"
        ref_path.write_text(f">reference\n{reference}\n")
        out_path = tmp_path / "output.txt"

        code, out, err = await asyncio.to_thread(_run_fastani, query_path, ref_path, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if not result_text.strip():
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "FastANI found no alignment between these sequences -- they may be too "
                        "divergent (ANI is undefined below roughly 80% identity) or too short for "
                        f"reliable estimation: {err.strip() or out.strip() or ''}"
                    ),
                }
            ]
        }

    fields = result_text.strip().split("\t")
    if len(fields) < 5:
        return {"content": [{"type": "text", "text": f"FastANI produced an unexpected output format: {result_text.strip()}"}]}

    _, _, ani, mapped_fragments, total_fragments = fields[:5]
    text = (
        f"FastANI Average Nucleotide Identity [fastani:ani]: {ani}% "
        f"({mapped_fragments}/{total_fragments} query fragments aligned)"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_fastani_similarity_mcp_server():
    return create_sdk_mcp_server(name="fastani_similarity", tools=[compute_genome_ani])
