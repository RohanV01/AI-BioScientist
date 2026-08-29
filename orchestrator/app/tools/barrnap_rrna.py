"""A real Barrnap MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Metagenomics cluster) -- subprocess-wrapped `barrnap` CLI
(apt `barrnap` package, see Dockerfile; its own transitive dependencies
-- `nhmmer` and `bedtools` -- confirmed live by extracting the real
.deb locally rather than assumed). Real ribosomal RNA gene prediction
(5S/16S/23S for bacteria, plus archaeal/eukaryotic/mitochondrial
models) using barrnap's own bundled HMM profiles -- no external
database needed. Fills a real gap: nothing else on this platform
predicts rRNA genes, the standard marker used for phylogenetic
placement and rapid organism identification (16S in particular).
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

VALID_KINGDOMS = {"bac", "arc", "euk", "mito"}
MAX_HITS_RETURNED = 20
GFF_ATTR_PRODUCT = re.compile(r"product=([^;]+)")
GFF_ATTR_NAME = re.compile(r"Name=([^;]+)")


def _run_barrnap(input_path: Path, kingdom: str) -> tuple[int, str, str]:
    proc = subprocess.run(["barrnap", "--kingdom", kingdom, str(input_path)], capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "predict_rrna_genes",
    "Given a nucleotide sequence (genome/contig) and a kingdom (bac, "
    "arc, euk, or mito -- default bac), predict ribosomal RNA genes "
    "(5S/16S/23S for bacteria, equivalent sets for other kingdoms) via "
    "Barrnap's HMM profiles. Returns each predicted rRNA gene's type, "
    "coordinates, strand, and match quality. Never state an rRNA gene "
    "prediction this tool didn't actually make.",
    {"sequence": str, "kingdom": str},
)
async def predict_rrna_genes(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    kingdom = args.get("kingdom") or "bac"
    if kingdom not in VALID_KINGDOMS:
        return {"content": [{"type": "text", "text": f"kingdom must be one of {sorted(VALID_KINGDOMS)}."}]}
    if len(sequence) < 200:
        return {"content": [{"type": "text", "text": "sequence must be at least 200bp -- rRNA genes themselves run 100-3000bp."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        code, out, err = await asyncio.to_thread(_run_barrnap, input_path, kingdom)

    if code != 0:
        return {"content": [{"type": "text", "text": f"Barrnap failed: {err.strip() or 'unknown error'}"}]}

    hits = []
    for line in out.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 9:
            continue
        _, _, _, start, end, score, strand, _, attrs = parts
        name_match = GFF_ATTR_NAME.search(attrs)
        product_match = GFF_ATTR_PRODUCT.search(attrs)
        hits.append(
            {
                "name": name_match.group(1) if name_match else "rRNA",
                "product": product_match.group(1) if product_match else "",
                "start": start,
                "end": end,
                "strand": strand,
                "score": score,
            }
        )

    if not hits:
        return {"content": [{"type": "text", "text": f"Barrnap found no {kingdom} rRNA genes in this sequence."}]}

    lines = [f"Barrnap rRNA predictions ({kingdom}) [barrnap:rrna] -- {len(hits)} gene(s):"]
    for h in hits[:MAX_HITS_RETURNED]:
        lines.append(f"- {h['name']} ({h['product']}): {h['start']}-{h['end']} ({h['strand']} strand), e-value {h['score']}")
    if len(hits) > MAX_HITS_RETURNED:
        lines.append(f"... and {len(hits) - MAX_HITS_RETURNED} more not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_barrnap_rrna_mcp_server():
    return create_sdk_mcp_server(name="barrnap_rrna", tools=[predict_rrna_genes])
