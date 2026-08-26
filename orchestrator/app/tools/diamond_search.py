"""A real DIAMOND MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Sequence analysis fundamentals cluster) -- subprocess-wrapped
`diamond` binary (downloaded as a prebuilt static binary in Dockerfile;
not in Debian's apt repos, same "not apt-installable, needs its own
Dockerfile step" class as hmmer/mafft precedents), same pattern as
blast_search.py.

Protein-only (DIAMOND's primary design target), and the same "query
against a caller-supplied reference set" shape as blast_search.py --
the real differentiator over BLAST+'s blastp is DIAMOND's much faster
double-indexed seed-and-extend algorithm at scale (its own published
benchmark: 100-20,000x faster than BLASTP on large protein databases),
which matters once a caller supplies a large reference set, not a
different underlying operation. Kept as a separate tool rather than
folded into blast_search because BLAST+ has no protein-scale-search
equivalent this platform can otherwise offer.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_diamond(query_path: Path, db_path: Path, tmp: str, max_results: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "diamond", "blastp", "-q", str(query_path), "-d", str(db_path),
            "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
            "--max-target-seqs", str(max_results), "--quiet",
        ],
        capture_output=True, text=True, timeout=60, cwd=tmp,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "diamond_search",
    "Given a protein query sequence and a dict of {name: reference_protein_sequence} "
    "to search against, run a real DIAMOND protein similarity search (a "
    "much faster alternative to BLAST+'s blastp for large reference "
    "sets) and return real hits with percent identity, alignment "
    "length, E-value, and bit score. Never state a hit/E-value this "
    "tool didn't actually compute.",
    {"query_sequence": str, "reference_sequences": dict, "max_results": int},
)
async def diamond_search(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query_sequence") or "").strip().upper()
    references = args.get("reference_sequences")
    max_results = min(int(args.get("max_results", 10)), 30)

    if not query:
        return {"content": [{"type": "text", "text": "query_sequence must not be empty."}]}
    if not isinstance(references, dict) or not references:
        return {"content": [{"type": "text", "text": "reference_sequences must be a non-empty dict of {name: sequence}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        query_path = tmp_path / "query.fasta"
        query_path.write_text(f">query\n{query}\n")

        db_input_path = tmp_path / "reference.fasta"
        db_input_path.write_text("\n".join(f">{name}\n{seq}" for name, seq in references.items()) + "\n")

        db_path = tmp_path / "refdb"
        makedb = subprocess.run(
            ["diamond", "makedb", "--in", str(db_input_path), "-d", str(db_path), "--quiet"],
            capture_output=True, text=True, timeout=30, cwd=tmp,
        )
        if makedb.returncode != 0:
            return {"content": [{"type": "text", "text": f"diamond makedb failed: {makedb.stderr.strip() or makedb.stdout.strip()}"}]}

        code, out, err = await asyncio.to_thread(_run_diamond, query_path, Path(f"{db_path}.dmnd"), tmp, max_results)

    if code != 0:
        return {"content": [{"type": "text", "text": f"diamond blastp failed: {err.strip() or 'unknown error'}"}]}
    if not out.strip():
        return {"content": [{"type": "text", "text": f"No significant DIAMOND hits found among the {len(references)} reference sequence(s)."}]}

    lines = [f"DIAMOND blastp [diamond:blastp] -- hits for query against {len(references)} reference sequence(s):"]
    for row in out.strip().splitlines()[:max_results]:
        parts = row.split("\t")
        if len(parts) != 6:
            continue
        _, sseqid, pident, length, evalue, bitscore = parts
        lines.append(f"- {sseqid}: {pident}% identity, {length}aa aligned, E-value {evalue}, bit score {bitscore}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_diamond_search_mcp_server():
    return create_sdk_mcp_server(name="diamond_search", tools=[diamond_search])
