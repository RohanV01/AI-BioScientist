"""A real Prokka MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `prokka` CLI
(apt `prokka` package, see Dockerfile). Real whole-genome prokaryotic
annotation (gene calling via Prodigal + functional annotation against
Prokka's own bundled ~104MB curated protein database -- no separate
DB download needed). Fills a real gap beyond `prodigal_genes`
(ab initio gene *coordinates* only): Prokka additionally assigns gene
names, EC numbers, and product descriptions to each predicted gene.

Real, confirmed-live gotcha fixed in the Dockerfile, not this file:
Debian's `prokka` package still hard-requires the discontinued NCBI
`tbl2asn` tool (removed from public download, hard-coded expiration) --
worked around by installing NCBI's own designated replacement,
`table2asn`, renamed to `tbl2asn`.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_GENES_RETURNED = 30


def _run_prokka(input_path: Path, out_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["prokka", "--outdir", str(out_dir), "--prefix", "result", "--cpus", "2", "--quiet", "--force", str(input_path)],
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "annotate_genome_prokka",
    "Given a prokaryotic (bacterial/archaeal) genome or contig "
    "nucleotide sequence, run Prokka for whole-genome annotation: gene "
    "calling plus functional annotation (gene name, EC number, product "
    "description) against Prokka's own curated protein database. "
    "Genuinely slow (a full annotation pipeline, not a lookup) -- "
    "minutes even for a modest sequence, do not abandon a call early on "
    "this basis alone. Never state a gene name, EC number, or product "
    "this tool didn't actually annotate.",
    {"sequence": str},
)
async def annotate_genome_prokka(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 200:
        return {"content": [{"type": "text", "text": "sequence must be at least 200bp -- Prokka needs enough sequence to detect real gene models."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        out_dir = tmp_path / "out"

        code, out, err = await asyncio.to_thread(_run_prokka, input_path, out_dir)
        tsv_path = out_dir / "result.tsv"
        tsv_text = tsv_path.read_text() if tsv_path.exists() else ""

    if not tsv_text.strip():
        return {"content": [{"type": "text", "text": f"Prokka annotation failed: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    rows = [r.split("\t") for r in tsv_text.strip().splitlines()]
    header, data_rows = rows[0], rows[1:]
    if not data_rows:
        return {"content": [{"type": "text", "text": "Prokka found no annotatable genes in this sequence."}]}

    lines = [f"Prokka whole-genome annotation [prokka:gene] -- {len(data_rows)} feature(s):"]
    for row in data_rows[:MAX_GENES_RETURNED]:
        record = dict(zip(header, row))
        gene = record.get("gene", "").strip()
        product = record.get("product", "").strip()
        ec = record.get("EC_number", "").strip()
        locus = record.get("locus_tag", "?")
        label = f"{gene} -- " if gene else ""
        ec_label = f" (EC {ec})" if ec else ""
        lines.append(f"- {locus}: {label}{product}{ec_label}")
    if len(data_rows) > MAX_GENES_RETURNED:
        lines.append(f"... and {len(data_rows) - MAX_GENES_RETURNED} more feature(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_prokka_annotate_mcp_server():
    return create_sdk_mcp_server(name="prokka_annotate", tools=[annotate_genome_prokka])
