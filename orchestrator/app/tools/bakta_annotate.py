"""A real Bakta MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
2, Metagenomics cluster) -- subprocess-wrapped `bakta` CLI (real PyPI
package). A newer, actively-developed alternative annotation pipeline
to `prokka_annotate` -- Bakta additionally cross-references PLSDB
(plasmids), ISfinder-derived insertion sequences, and oriC/oriT
origins that Prokka's own database doesn't cover, so this isn't a
duplicate of the Prokka tool.

Ships Bakta's own official "light" reference database (~1.3GB, baked
into the image at build time -- see Dockerfile) rather than the ~30GB
"full" database, per Bakta's own documented light/full tradeoff (full
adds PSC/PSCC cluster-based annotation for higher sensitivity) --
stated plainly so a caller doesn't expect full-DB-level sensitivity.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

BAKTA_DB = "/opt/bakta_db"
MAX_GENES_RETURNED = 30


def _run_bakta(input_path: Path, out_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["bakta", "--db", BAKTA_DB, "--output", str(out_dir), "--prefix", "result", "--threads", "2", "--force", str(input_path)],
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "annotate_genome_bakta",
    "Given a prokaryotic (bacterial/archaeal) genome or contig "
    "nucleotide sequence, run Bakta for whole-genome annotation (gene "
    "calling + functional annotation against Bakta's own reference "
    "database, using the 'light' DB tier -- reduced sensitivity versus "
    "Bakta's full DB, stated for calibration). Genuinely slow, do not "
    "abandon a call early on this basis alone. Never state a gene "
    "name, product, or annotation this tool didn't actually make.",
    {"sequence": str},
)
async def annotate_genome_bakta(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 200:
        return {"content": [{"type": "text", "text": "sequence must be at least 200bp -- Bakta needs enough sequence to detect real gene models."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        out_dir = tmp_path / "out"

        code, out, err = await asyncio.to_thread(_run_bakta, input_path, out_dir)
        tsv_path = out_dir / "result.tsv"
        tsv_text = tsv_path.read_text() if tsv_path.exists() else ""

    if not tsv_text.strip():
        return {"content": [{"type": "text", "text": f"Bakta annotation failed: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    # Bakta's .tsv has a few '#'-prefixed metadata/header lines before
    # the real tab-separated header row.
    data_lines = [line for line in tsv_text.strip().splitlines() if not line.startswith("##")]
    if not data_lines:
        return {"content": [{"type": "text", "text": "Bakta produced no parseable annotation output."}]}
    header_line = data_lines[0].lstrip("#")
    rows = [line.split("\t") for line in data_lines[1:]]
    header = header_line.split("\t")

    if not rows:
        return {"content": [{"type": "text", "text": "Bakta found no annotatable genes in this sequence."}]}

    lines = [f"Bakta whole-genome annotation (light DB) [bakta:gene] -- {len(rows)} feature(s):"]
    for row in rows[:MAX_GENES_RETURNED]:
        record = dict(zip(header, row))
        gene = record.get("Gene", "").strip()
        product = record.get("Product", "").strip()
        locus = record.get("Locus Tag", "?")
        ftype = record.get("Type", "")
        label = f"{gene} -- " if gene else ""
        lines.append(f"- {locus} ({ftype}): {label}{product}")
    if len(rows) > MAX_GENES_RETURNED:
        lines.append(f"... and {len(rows) - MAX_GENES_RETURNED} more feature(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_bakta_annotate_mcp_server():
    return create_sdk_mcp_server(name="bakta_annotate", tools=[annotate_genome_bakta])
