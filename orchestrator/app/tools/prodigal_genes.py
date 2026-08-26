"""A real Prodigal MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Sequence analysis fundamentals cluster) -- subprocess-wrapped
`prodigal` CLI (apt `prodigal` package, see Dockerfile), real
prokaryotic (bacterial/archaeal) gene-calling from a genome/contig
sequence. Fills a genuine gap -- nothing else on this platform predicts
protein-coding genes from raw nucleotide sequence; every other tool
here (ensembl, uniprot, alphafold, ...) assumes a gene/protein already
has a known identifier or a curated annotation.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_GENES_RETURNED = 30


def _run_prodigal(input_path: Path, genes_path: Path, proteins_path: Path) -> tuple[int, str, str]:
    # -p meta: uses Prodigal's pre-trained generic models instead of
    # training a new one on the input -- single-genome mode (the
    # default) needs a long, complete genome to train on and performs
    # poorly or fails outright on a short contig or partial sequence, a
    # realistic caller input for a chat tool.
    proc = subprocess.run(
        ["prodigal", "-i", str(input_path), "-a", str(proteins_path), "-o", str(genes_path), "-f", "gff", "-p", "meta", "-q"],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_gff_genes(gff_text: str) -> list[dict]:
    genes = []
    for line in gff_text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 9 or parts[2] != "CDS":
            continue
        genes.append({"start": int(parts[3]), "end": int(parts[4]), "strand": parts[6]})
    return genes


def _parse_fasta(text: str) -> list[str]:
    sequences = []
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if chunks:
                sequences.append("".join(chunks))
            chunks = []
        else:
            chunks.append(line.strip())
    if chunks:
        sequences.append("".join(chunks))
    return sequences


@tool(
    "predict_genes",
    "Given a prokaryotic (bacterial/archaeal) genome or contig "
    "nucleotide sequence, run Prodigal to predict protein-coding genes "
    "-- real ab initio gene calling, not a lookup. Returns each "
    "predicted gene's coordinates, strand, and translated protein "
    "sequence. Never state a gene coordinate or translated sequence "
    "this tool didn't actually predict.",
    {"sequence": str},
)
async def predict_genes(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 200:
        return {"content": [{"type": "text", "text": "sequence must be at least 200bp -- Prodigal needs enough sequence to detect real gene models."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        genes_path = tmp_path / "genes.gff"
        proteins_path = tmp_path / "proteins.faa"

        code, out, err = await asyncio.to_thread(_run_prodigal, input_path, genes_path, proteins_path)
        gff_text = genes_path.read_text() if genes_path.exists() else ""
        proteins_text = proteins_path.read_text() if proteins_path.exists() else ""

    if code != 0:
        return {"content": [{"type": "text", "text": f"Prodigal gene prediction failed: {err.strip() or 'unknown error'}"}]}

    genes = _parse_gff_genes(gff_text)
    proteins = _parse_fasta(proteins_text)
    if not genes:
        return {"content": [{"type": "text", "text": "Prodigal found no predicted genes in this sequence."}]}

    lines = [f"Prodigal [prodigal:cds] -- {len(genes)} predicted gene(s):"]
    for i, (gene, protein) in enumerate(zip(genes[:MAX_GENES_RETURNED], proteins[:MAX_GENES_RETURNED])):
        lines.append(f"- gene {i + 1}: {gene['start']}-{gene['end']} ({gene['strand']} strand), protein: {protein}")
    if len(genes) > MAX_GENES_RETURNED:
        lines.append(f"... and {len(genes) - MAX_GENES_RETURNED} more gene(s) not shown.")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_prodigal_genes_mcp_server():
    return create_sdk_mcp_server(name="prodigal_genes", tools=[predict_genes])
