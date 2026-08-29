"""A real Kraken2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `kraken2` CLI
(apt `kraken2` package, see Dockerfile), real k-mer-based taxonomic
classification of a nucleotide sequence.

Ships the real k2_viral reference database (~570MB, baked into the
image at build time -- see Dockerfile) rather than the ~8-16GB
standard/pluspf databases, keeping this already-large cluster's image
growth in check for a platform meant to be cloned and built by any
researcher. This scopes real classification to viral sequences --
stated plainly in the tool description so a caller doesn't expect
bacterial/archaeal hits. Fills a real gap: nothing else on this
platform answers "what organism does this sequence most likely come
from" from raw sequence alone.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

KRAKEN2_DB = "/opt/kraken2_db"
MAX_TAXA_RETURNED = 20


def _run_kraken2(input_path: Path, report_path: Path, output_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["kraken2", "--db", KRAKEN2_DB, "--use-names", "--report", str(report_path), "--output", str(output_path), str(input_path)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "classify_sequence_kraken2",
    "Given a nucleotide sequence (e.g. a metagenomic contig or read), "
    "classify it via Kraken2 exact k-mer matching against a real viral "
    "reference database (this tool's database is scoped to viruses -- "
    "it will not identify bacterial/archaeal/eukaryotic sequences). "
    "Returns the taxonomic breakdown of k-mer hits by rank. Never state "
    "a taxonomic classification this tool didn't actually compute.",
    {"sequence": str},
)
async def classify_sequence_kraken2(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 50:
        return {"content": [{"type": "text", "text": "sequence must be at least 50bp for meaningful k-mer classification."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        report_path = tmp_path / "report.txt"
        output_path = tmp_path / "output.txt"

        code, out, err = await asyncio.to_thread(_run_kraken2, input_path, report_path, output_path)
        report_text = report_path.read_text() if report_path.exists() else ""

    if code != 0:
        return {"content": [{"type": "text", "text": f"Kraken2 classification failed: {err.strip() or 'unknown error'}"}]}
    if not report_text.strip():
        return {"content": [{"type": "text", "text": "Kraken2 ran but produced no report."}]}

    rows = [r.split("\t") for r in report_text.strip().splitlines()]
    hit_rows = [r for r in rows if len(r) == 6 and r[3] != "U" and float(r[0]) > 0]
    if not hit_rows:
        return {"content": [{"type": "text", "text": "Kraken2 found no matches in the (virus-scoped) reference database for this sequence -- it may be non-viral or absent from this tool's k2_viral database."}]}

    lines = ["Kraken2 taxonomic classification (viral reference DB) [kraken2:taxon] -- top hits:"]
    for row in sorted(hit_rows, key=lambda r: -float(r[0]))[:MAX_TAXA_RETURNED]:
        pct, clade_reads, direct_reads, rank, taxid, name = row
        lines.append(f"- {name.strip()} (taxid {taxid}, rank {rank}): {pct}% of k-mers")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_kraken2_classify_mcp_server():
    return create_sdk_mcp_server(name="kraken2_classify", tools=[classify_sequence_kraken2])
