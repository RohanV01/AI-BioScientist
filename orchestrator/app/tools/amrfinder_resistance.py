"""A real AMRFinderPlus MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `amrfinder` CLI
(NCBI's own prebuilt static Linux binary release, not apt/pip
installable, confirmed live -- see Dockerfile). Real detection of
acquired antimicrobial resistance genes, plus stress/biocide/virulence
factors, from a nucleotide or protein sequence via NCBI's own curated
Reference Gene Catalog (the reference database this platform's
`clinpgx_annotations`/`clinvar` don't cover -- those are human
pharmacogenomic/clinical variants, not microbial resistance genes).
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

AMRFINDER_DB = "/opt/amrfinder/data"
MAX_HITS_RETURNED = 20


def _run_amrfinder(input_path: Path, out_path: Path, is_nucleotide: bool) -> tuple[int, str, str]:
    flag = "-n" if is_nucleotide else "-p"
    proc = subprocess.run(
        ["amrfinder", flag, str(input_path), "-d", AMRFINDER_DB, "-o", str(out_path), "--plus"],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "detect_resistance_genes",
    "Given a nucleotide or protein sequence and whether it's "
    "nucleotide (is_nucleotide=true) or protein (false), detect real "
    "acquired antimicrobial resistance genes plus stress/biocide/"
    "virulence factors via AMRFinderPlus, against NCBI's own curated "
    "Reference Gene Catalog. Never state a resistance gene or drug "
    "class this tool didn't actually detect.",
    {"sequence": str, "is_nucleotide": bool},
)
async def detect_resistance_genes(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    is_nucleotide = bool(args.get("is_nucleotide", True))
    if len(sequence) < 50:
        return {"content": [{"type": "text", "text": "sequence must be at least 50 residues/bases."}]}
    valid_chars = set("ACGTN") if is_nucleotide else set("ACDEFGHIKLMNPQRSTVWYX*")
    if not set(sequence) <= valid_chars:
        return {"content": [{"type": "text", "text": f"sequence contains characters invalid for {'nucleotide' if is_nucleotide else 'protein'} input."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / ("input.fasta" if is_nucleotide else "input.faa")
        input_path.write_text(f">query\n{sequence}\n")
        out_path = tmp_path / "output.tsv"

        code, out, err = await asyncio.to_thread(_run_amrfinder, input_path, out_path, is_nucleotide)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0:
        return {"content": [{"type": "text", "text": f"AMRFinderPlus failed: {err.strip()[-1000:] or 'unknown error'}"}]}

    rows = [r.split("\t") for r in result_text.strip().splitlines()] if result_text.strip() else []
    if len(rows) < 2:
        return {"content": [{"type": "text", "text": "AMRFinderPlus found no resistance/stress/virulence genes in this sequence."}]}

    header, data_rows = rows[0], rows[1:]
    lines = [f"AMRFinderPlus resistance gene detection [amrfinder:gene] -- {len(data_rows)} hit(s):"]
    for row in data_rows[:MAX_HITS_RETURNED]:
        record = dict(zip(header, row))
        gene = record.get("Gene symbol", "?")
        product = record.get("Sequence name", "")
        element_type = record.get("Element type", "")
        drug_class = record.get("Class", "")
        identity = record.get("% Identity to reference", "?")
        lines.append(f"- {gene} ({element_type}, class {drug_class}): {product} -- {identity}% identity to reference")
    if len(data_rows) > MAX_HITS_RETURNED:
        lines.append(f"... and {len(data_rows) - MAX_HITS_RETURNED} more hit(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_amrfinder_resistance_mcp_server():
    return create_sdk_mcp_server(name="amrfinder_resistance", tools=[detect_resistance_genes])
