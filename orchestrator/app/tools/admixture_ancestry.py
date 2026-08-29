"""A real ADMIXTURE MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Population genetics cluster) -- subprocess-wrapped `admixture`
CLI (real prebuilt static binary, see Dockerfile -- not apt/pip
installable, confirmed live). Real maximum-likelihood ancestry
inference (unsupervised model-based clustering, the standard
"ADMIXTURE plot" analysis) from a genotype matrix, given a caller-chosen
number of ancestral populations K.

ADMIXTURE's real input is PLINK's binary .bed/.bim/.fam trio, not a
text format -- built directly here (real 2-bit-per-genotype SNP-major
packing per PLINK's own spec) from a simple {sample: dosages} dict, the
same "construct the real binary/text input format a CLI tool expects
from simple caller-supplied data" pattern as blast_search/mummer_align.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

VALID_GENOTYPE_CODES = {0, 1, 2, 9}
MAX_K = 10


def _pack_bed(genotype_matrix: list[list[int]]) -> bytes:
    """genotype_matrix[snp_idx][sample_idx] -> dosage (0/1/2/9). Real
    PLINK .bed SNP-major 2-bit packing: 00=hom A1, 01=missing,
    10=het, 11=hom A2; 4 samples per byte, first sample in the low bits."""
    code_map = {0: 0b00, 1: 0b10, 2: 0b11, 9: 0b01}
    body = bytearray()
    for snp_row in genotype_matrix:
        for chunk_start in range(0, len(snp_row), 4):
            chunk = snp_row[chunk_start:chunk_start + 4]
            byte = 0
            for i, dosage in enumerate(chunk):
                byte |= code_map[dosage] << (i * 2)
            body.append(byte)
    return bytes([0x6C, 0x1B, 0x01]) + bytes(body)


def _run_admixture(bed_path: Path, k: int, work_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["admixture", bed_path.name, str(k)], capture_output=True, text=True, timeout=300, cwd=str(work_dir))
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "infer_ancestry",
    "Given a dict of {sample_id: [genotype_dosage, ...]} (0/1/2 alt "
    "allele copies per SNP, 9 for missing; all samples must list the "
    "same SNPs in the same order) and a number of ancestral populations "
    "K, run ADMIXTURE to infer each sample's real maximum-likelihood "
    "ancestry fractions across K clusters (the standard unsupervised "
    "'ADMIXTURE plot' analysis). Never state an ancestry fraction this "
    "tool didn't actually compute.",
    {"samples": dict, "k": int},
)
async def infer_ancestry(args: dict[str, Any]) -> dict[str, Any]:
    samples = args.get("samples")
    k = args.get("k")
    if not isinstance(samples, dict) or len(samples) < 4:
        return {"content": [{"type": "text", "text": "samples must be a dict of at least 4 {sample_id: [dosages]} entries."}]}
    if not isinstance(k, int) or not (2 <= k <= MAX_K):
        return {"content": [{"type": "text", "text": f"k must be an integer between 2 and {MAX_K}."}]}
    if k >= len(samples):
        return {"content": [{"type": "text", "text": f"k ({k}) must be smaller than the number of samples ({len(samples)})."}]}

    lengths = set()
    for sample_id, dosages in samples.items():
        if not isinstance(dosages, list) or not dosages:
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' must map to a non-empty list of genotype dosages."}]}
        if not all(d in VALID_GENOTYPE_CODES for d in dosages):
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' dosages must only contain 0, 1, 2, or 9 (missing)."}]}
        lengths.add(len(dosages))
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"all samples must list the same number of SNPs -- got lengths {sorted(lengths)}."}]}
    n_snps = lengths.pop()

    sample_ids = list(samples.keys())
    genotype_matrix = [[samples[sid][snp_idx] for sid in sample_ids] for snp_idx in range(n_snps)]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bed_path = tmp_path / "input.bed"
        bim_path = tmp_path / "input.bim"
        fam_path = tmp_path / "input.fam"

        bed_path.write_bytes(_pack_bed(genotype_matrix))
        bim_path.write_text("".join(f"1\tsnp{i}\t0\t{(i + 1) * 1000}\tA\tB\n" for i in range(n_snps)))
        fam_path.write_text("".join(f"{sid}\t{sid}\t0\t0\t0\t-9\n" for sid in sample_ids))

        code, out, err = await asyncio.to_thread(_run_admixture, bed_path, k, tmp_path)
        q_path = tmp_path / f"input.{k}.Q"
        q_text = q_path.read_text() if q_path.exists() else ""

    if not q_text.strip():
        return {"content": [{"type": "text", "text": f"ADMIXTURE failed to produce ancestry estimates: {err.strip() or out.strip() or 'unknown error'}"}]}

    lines = [f"ADMIXTURE ancestry fractions (K={k}) [admixture:ancestry]:"]
    for sample_id, row in zip(sample_ids, q_text.strip().splitlines()):
        fractions = [f"pop{i + 1}={v}" for i, v in enumerate(row.split())]
        lines.append(f"- {sample_id}: {', '.join(fractions)}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_admixture_ancestry_mcp_server():
    return create_sdk_mcp_server(name="admixture_ancestry", tools=[infer_ancestry])
