"""A real CheckM2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `checkm2` CLI
(real PyPI package). Real machine-learning-based completeness/
contamination estimation for a genome bin/assembly (the standard QC
step in metagenomic binning -- "is this assembled genome actually a
complete, uncontaminated single organism"), against CheckM2's own real
DIAMOND reference database (~1.7GB, baked into the image at build time
-- see Dockerfile). Fills a real gap: nothing else on this platform
assesses assembly quality before downstream analysis (annotation,
taxonomic placement) is trusted.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

CHECKM2_DB = "/opt/checkm2_db"


def _find_db_file(db_dir: str) -> str:
    matches = list(Path(db_dir).rglob("*.dmnd"))
    return str(matches[0]) if matches else db_dir


def _run_checkm2(input_path: Path, out_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "checkm2", "predict", "--input", str(input_path), "--output-directory", str(out_dir),
            "--database_path", _find_db_file(CHECKM2_DB), "-x", "fasta", "--force", "--threads", "2",
        ],
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "assess_genome_quality",
    "Given a genome bin/assembly nucleotide sequence (a single "
    "organism's assembled contigs, concatenated), assess its real "
    "completeness and contamination via CheckM2's machine-learning "
    "model (trained on real single-copy marker gene content) -- the "
    "standard QC check before trusting a metagenome-assembled genome. "
    "Never state a completeness or contamination percentage this tool "
    "didn't actually compute.",
    {"sequence": str},
)
async def assess_genome_quality(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 5000:
        return {"content": [{"type": "text", "text": "sequence must be at least 5000bp -- CheckM2's marker-gene model needs a substantial genome bin, not a short fragment."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_dir = tmp_path / "genomes"
        input_dir.mkdir()
        (input_dir / "bin.fasta").write_text(f">query\n{sequence}\n")
        out_dir = tmp_path / "out"

        code, out, err = await asyncio.to_thread(_run_checkm2, input_dir, out_dir)
        report_path = out_dir / "quality_report.tsv"
        report_text = report_path.read_text() if report_path.exists() else ""

    if not report_text.strip():
        return {"content": [{"type": "text", "text": f"CheckM2 quality assessment failed: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(report_text), delimiter="\t"))
    if not rows:
        return {"content": [{"type": "text", "text": "CheckM2 produced no quality report row for this bin."}]}

    row = rows[0]
    completeness = row.get("Completeness", "?")
    contamination = row.get("Contamination", "?")
    coding_density = row.get("Coding_Density", "?")
    genome_size = row.get("Genome_Size", "?")

    text = (
        f"CheckM2 genome quality assessment [checkm2:quality]:\n"
        f"- Completeness: {completeness}%\n"
        f"- Contamination: {contamination}%\n"
        f"- Coding density: {coding_density}\n"
        f"- Genome size: {genome_size}bp"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_checkm2_quality_mcp_server():
    return create_sdk_mcp_server(name="checkm2_quality", tools=[assess_genome_quality])
