"""A real CheckV MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `checkv` CLI
(real PyPI package). Real viral genome quality assessment (completeness
estimation via CheckV's own curated set of complete reference viral
genomes, contamination/host-gene detection, provirus boundary
trimming) against CheckV's official reference database (~1.7GB, baked
into the image at build time -- see Dockerfile). Distinct from
`checkm2_quality` (prokaryotic/bacterial genome bins, marker-gene-based)
-- CheckV is purpose-built for viral contigs, which have no universal
single-copy marker genes to base a CheckM2-style estimate on.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

CHECKV_DB = "/opt/checkv_db"


def _run_checkv(input_path: Path, out_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["checkv", "end_to_end", str(input_path), str(out_dir), "-d", CHECKV_DB, "-t", "2"],
        capture_output=True, text=True, timeout=180,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "assess_viral_genome_quality",
    "Given a viral contig nucleotide sequence, assess its real "
    "completeness and contamination via CheckV (completeness estimated "
    "against CheckV's curated complete-reference-genome set; "
    "contamination flags non-viral/host gene content; also reports "
    "CheckV's own quality tier). Never state a completeness percentage "
    "or quality tier this tool didn't actually compute.",
    {"sequence": str},
)
async def assess_viral_genome_quality(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 500:
        return {"content": [{"type": "text", "text": "sequence must be at least 500bp -- too short for CheckV's gene-based quality model."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        out_dir = tmp_path / "out"

        code, out, err = await asyncio.to_thread(_run_checkv, input_path, out_dir)
        summary_path = out_dir / "quality_summary.tsv"
        summary_text = summary_path.read_text() if summary_path.exists() else ""

    if not summary_text.strip():
        return {"content": [{"type": "text", "text": f"CheckV quality assessment failed: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(summary_text), delimiter="\t"))
    if not rows:
        return {"content": [{"type": "text", "text": "CheckV produced no quality summary row for this sequence."}]}

    row = rows[0]
    completeness = row.get("completeness", "not estimated")
    contamination = row.get("contamination", "?")
    quality = row.get("checkv_quality", "?")
    gene_count = row.get("gene_count", "?")
    warnings = row.get("warnings", "")

    text = (
        f"CheckV viral genome quality assessment [checkv:quality]:\n"
        f"- CheckV quality tier: {quality}\n"
        f"- Estimated completeness: {completeness}%\n"
        f"- Contamination: {contamination}%\n"
        f"- Predicted genes: {gene_count}"
    )
    if warnings:
        text += f"\n- Warnings: {warnings}"

    return {"content": [{"type": "text", "text": text}]}


def build_checkv_quality_mcp_server():
    return create_sdk_mcp_server(name="checkv_quality", tools=[assess_viral_genome_quality])
