"""A real EIGENSOFT MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Population genetics cluster) -- subprocess-wrapped `smartpca`
CLI (apt `eigensoft` package, see Dockerfile), real PCA-based
population-structure inference from genotype data (Patterson et al.
2006's EIGENSTRAT method). Fills a real gap: nothing else on this
platform reduces a genotype matrix to principal components for
visualizing/quantifying population structure or sample stratification.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

VALID_GENOTYPE_CODES = {0, 1, 2, 9}  # 9 = missing, EIGENSTRAT convention
MAX_PC_RETURNED = 5


def _run_smartpca(param_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["smartpca", "-p", str(param_path)], capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "compute_population_pca",
    "Given a dict of {sample_id: {\"population\": str, \"genotypes\": "
    "[0|1|2|9, ...]}} (genotype dosage per SNP -- 0/1/2 = copies of the "
    "alt allele, 9 = missing; all samples must list the same SNPs in "
    "the same order), compute real principal components of population "
    "structure via EIGENSOFT's smartpca (the standard EIGENSTRAT "
    "method). Returns each sample's coordinates on the top principal "
    "components. Never state a PC coordinate or eigenvalue this tool "
    "didn't actually compute.",
    {"samples": dict},
)
async def compute_population_pca(args: dict[str, Any]) -> dict[str, Any]:
    samples = args.get("samples")
    if not isinstance(samples, dict) or len(samples) < 4:
        return {"content": [{"type": "text", "text": "samples must be a dict of at least 4 {sample_id: {population, genotypes}} entries -- PCA needs several samples to be meaningful."}]}

    lengths = set()
    for sample_id, info in samples.items():
        if not isinstance(info, dict) or "genotypes" not in info or "population" not in info:
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' must have both 'population' and 'genotypes' keys."}]}
        genotypes = info["genotypes"]
        if not isinstance(genotypes, list) or not genotypes:
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' genotypes must be a non-empty list."}]}
        if not all(g in VALID_GENOTYPE_CODES for g in genotypes):
            return {"content": [{"type": "text", "text": f"sample '{sample_id}' genotypes must only contain 0, 1, 2, or 9 (missing)."}]}
        lengths.add(len(genotypes))
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"all samples must list the same number of SNPs -- got lengths {sorted(lengths)}."}]}
    n_snps = lengths.pop()

    sample_ids = list(samples.keys())
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        geno_path = tmp_path / "input.geno"
        snp_path = tmp_path / "input.snp"
        ind_path = tmp_path / "input.ind"
        evec_path = tmp_path / "output.evec"
        eval_path = tmp_path / "output.eval"
        param_path = tmp_path / "params.txt"

        # EIGENSTRAT .geno: one line per SNP, one genotype-dosage digit
        # per sample (no delimiter) -- real format, confirmed against
        # EIGENSOFT's own documentation, not guessed.
        geno_lines = []
        for snp_idx in range(n_snps):
            geno_lines.append("".join(str(samples[sid]["genotypes"][snp_idx]) for sid in sample_ids))
        geno_path.write_text("\n".join(geno_lines) + "\n")

        # .snp: SNPID Chr GeneticPos PhysicalPos Ref Alt -- physical
        # coordinates are fabricated (chr 1, incrementing position) since
        # the caller supplies genotype dosages, not real coordinates;
        # smartpca's PCA only uses the genotype matrix itself.
        snp_lines = [f"snp{i}  1  0.0  {(i + 1) * 1000}  A  B" for i in range(n_snps)]
        snp_path.write_text("\n".join(snp_lines) + "\n")

        ind_lines = [f"{sid}  U  {samples[sid]['population']}" for sid in sample_ids]
        ind_path.write_text("\n".join(ind_lines) + "\n")

        num_evec = min(10, len(sample_ids) - 1)
        param_path.write_text(
            f"genotypename: {geno_path}\n"
            f"snpname: {snp_path}\n"
            f"indivname: {ind_path}\n"
            f"evecoutname: {evec_path}\n"
            f"evaloutname: {eval_path}\n"
            f"numoutevec: {num_evec}\n"
        )

        code, out, err = await asyncio.to_thread(_run_smartpca, param_path)
        evec_text = evec_path.read_text() if evec_path.exists() else ""
        eval_text = eval_path.read_text() if eval_path.exists() else ""

    if not evec_text.strip():
        return {"content": [{"type": "text", "text": f"smartpca failed to produce output: {err.strip() or out.strip() or 'unknown error'}"}]}

    eigenvalues = [v.strip() for v in eval_text.splitlines() if v.strip()][:MAX_PC_RETURNED]
    lines = [f"EIGENSOFT smartpca population PCA [eigensoft:pca] -- {len(sample_ids)} samples, top {min(num_evec, MAX_PC_RETURNED)} PCs shown:"]
    if eigenvalues:
        lines.append(f"Eigenvalues (PC1..PC{len(eigenvalues)}): {', '.join(eigenvalues)}")

    for line in evec_text.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        sample_id, *pcs = parts
        pcs_shown = pcs[:MAX_PC_RETURNED]
        lines.append(f"- {sample_id}: {', '.join(f'PC{i + 1}={v}' for i, v in enumerate(pcs_shown))}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_eigensoft_pca_mcp_server():
    return create_sdk_mcp_server(name="eigensoft_pca", tools=[compute_population_pca])
