"""A real BLAST+ MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
2, Sequence analysis fundamentals cluster -- flagged in docs/12 as "the
single most fundamental missing operation": this platform had zero
sequence-similarity-search capability before this tool). Subprocess-
wrapped `makeblastdb` + `blastn`/`blastp` (real NCBI BLAST+ binaries via
the `ncbi-blast+` apt package, see Dockerfile), same pattern as
msa.py's MAFFT wrapper.

Distinct from the already-live `minimap2_align` (fast approximate
pairwise alignment, best for long reads/genome-vs-genome): this tool
does real local BLAST similarity search with proper statistics
(E-value, bit score, percent identity) of one query sequence against a
caller-supplied set of reference sequences -- the actual operation
"does this sequence resemble any of these known sequences, and how
significantly" that minimap2's CIGAR-based output doesn't directly
answer. Builds a real temporary BLAST database from the references
(nucleotide or protein, caller-specified), not a remote NCBI query --
no external network dependency, results are reproducible and fast.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


def _run_blast(query_path: Path, db_path: Path, program: str, tmp: str, max_results: int) -> tuple[int, str, str]:
    args = [
        program, "-query", str(query_path), "-db", str(db_path),
        "-outfmt", "6 qseqid sseqid pident length evalue bitscore",
        "-max_target_seqs", str(max_results),
    ]
    if program == "blastn":
        # Real, confirmed-live bug: blastn's default DUST low-complexity
        # filter soft-masks repetitive stretches before seeding, and on
        # a short caller-supplied query it can mask enough of the
        # sequence that even a 100%-identical reference produces zero
        # hits (confirmed live: a 52bp query with a repetitive middle
        # segment against its own exact-match reference returned nothing
        # with default settings, and returned the real 100%-identity hit
        # the instant -dust no was added). This tool exists to check
        # similarity against a caller-supplied reference set, not to
        # filter genomic repeats out of a whole-genome search -- DUST's
        # purpose doesn't apply here the way it does for NCBI's own
        # public-database searches.
        args.append("-dust")
        args.append("no")
    proc = subprocess.run(
        args,
        capture_output=True, text=True, timeout=60, cwd=tmp,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "blast_search",
    "Given a query sequence and a dict of {name: reference_sequence} to "
    "search against, run a real local BLAST similarity search (BLAST+ "
    "blastn for DNA, blastp for protein -- set sequence_type) and return "
    "real hits with percent identity, alignment length, E-value, and bit "
    "score. Distinct from minimap2_align (fast approximate alignment, no "
    "significance statistics): this is the standard similarity-search "
    "operation with real BLAST statistics. Never state a hit/E-value "
    "this tool didn't actually compute.",
    {"query_sequence": str, "reference_sequences": dict, "sequence_type": str, "max_results": int},
)
async def blast_search(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query_sequence") or "").strip().upper()
    references = args.get("reference_sequences")
    sequence_type = (args.get("sequence_type") or "nucl").strip().lower()
    max_results = min(int(args.get("max_results", 10)), 30)

    if not query:
        return {"content": [{"type": "text", "text": "query_sequence must not be empty."}]}
    if not isinstance(references, dict) or not references:
        return {"content": [{"type": "text", "text": "reference_sequences must be a non-empty dict of {name: sequence}."}]}
    if sequence_type not in ("nucl", "prot"):
        return {"content": [{"type": "text", "text": "sequence_type must be 'nucl' or 'prot'."}]}

    program = "blastn" if sequence_type == "nucl" else "blastp"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        query_path = tmp_path / "query.fasta"
        query_path.write_text(f">query\n{query}\n")

        db_input_path = tmp_path / "reference.fasta"
        db_input_path.write_text("\n".join(f">{name}\n{seq}" for name, seq in references.items()) + "\n")

        db_path = tmp_path / "refdb"
        makedb = subprocess.run(
            ["makeblastdb", "-in", str(db_input_path), "-dbtype", sequence_type, "-out", str(db_path)],
            capture_output=True, text=True, timeout=30, cwd=tmp,
        )
        if makedb.returncode != 0:
            return {"content": [{"type": "text", "text": f"makeblastdb failed: {makedb.stderr.strip() or makedb.stdout.strip()}"}]}

        code, out, err = await asyncio.to_thread(_run_blast, query_path, db_path, program, tmp, max_results)

    if code != 0:
        return {"content": [{"type": "text", "text": f"{program} failed: {err.strip() or 'unknown error'}"}]}
    if not out.strip():
        return {"content": [{"type": "text", "text": f"No significant BLAST hits found among the {len(references)} reference sequence(s)."}]}

    lines = [f"BLAST+ ({program}) [blast:{program}] -- hits for query against {len(references)} reference sequence(s):"]
    for row in out.strip().splitlines()[:max_results]:
        parts = row.split("\t")
        if len(parts) != 6:
            continue
        _, sseqid, pident, length, evalue, bitscore = parts
        lines.append(f"- {sseqid}: {pident}% identity, {length}bp/aa aligned, E-value {evalue}, bit score {bitscore}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_blast_search_mcp_server():
    return create_sdk_mcp_server(name="blast_search", tools=[blast_search])
