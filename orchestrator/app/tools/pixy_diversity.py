"""A real pixy MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
2 Population genetics cluster -- re-investigated after the earlier
bioconda-only rejection). Confirmed live: `pixy` is genuinely PyPI-
namesquatted (the PyPI package is an unrelated terminal-color library)
and only conda-forge-published as a CLI, BUT it's real, actively-
maintained pure Python underneath (Poetry-managed, real PyPI-hosted
deps: numpy, scikit-allel, numcodecs) -- confirmed by reading its own
source. Installed here via `pip install git+https://github.com/...`
rather than standing up a whole new conda/mamba toolchain just for one
tool, and its real internal vectorized functions (`calc_pi`, `calc_dxy`
from `pixy.calc`) are called in-process on a caller-built scikit-allel
GenotypeArray -- no VCF file needed, sidestepping pixy's own CLI
entirely (which is VCF-only).

Real gap this fills: unbiased nucleotide diversity (pi, within a
population) and divergence (dxy, between populations) -- distinct from
`egglib_popgen` (different diversity-statistics engine/estimator) and
from `poolfstat_fst`/`fastani_similarity` (Fst and whole-genome
identity are different statistics entirely).
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_SAMPLES_PER_POP = 100
MAX_SNPS = 2000


def _validate_population(pop_name: str, samples: Any) -> str | None:
    if not isinstance(samples, dict) or len(samples) < 1:
        return f"population '{pop_name}' must map to a non-empty dict of {{sample_id: [[a1, a2], ...]}}."
    if len(samples) > MAX_SAMPLES_PER_POP:
        return f"population '{pop_name}' has {len(samples)} samples -- at most {MAX_SAMPLES_PER_POP}."
    lengths = set()
    for sample_id, genotypes in samples.items():
        if not isinstance(genotypes, list) or not genotypes:
            return f"population '{pop_name}' sample '{sample_id}' must be a non-empty list of [allele1, allele2] genotype calls."
        for gt in genotypes:
            if not (isinstance(gt, list) and len(gt) == 2 and all(a in (0, 1, -1) for a in gt)):
                return f"population '{pop_name}' sample '{sample_id}' has an invalid genotype call -- each must be [a1, a2] with alleles 0, 1, or -1 (missing)."
        lengths.add(len(genotypes))
    if len(lengths) != 1:
        return f"population '{pop_name}': all samples must have the same number of SNP genotype calls -- got lengths {sorted(lengths)}."
    n_snps = lengths.pop()
    if n_snps > MAX_SNPS:
        return f"population '{pop_name}' has {n_snps} SNPs -- at most {MAX_SNPS}."
    return None


def _build_gt_array(samples: dict):
    import allel

    sample_ids = list(samples.keys())
    n_snps = len(samples[sample_ids[0]])
    # (n_variants, n_samples, ploidy=2) -- real scikit-allel GenotypeArray shape.
    calls = [[samples[sid][snp_idx] for sid in sample_ids] for snp_idx in range(n_snps)]
    return allel.GenotypeArray(calls)


@tool(
    "compute_nucleotide_diversity",
    "Given a dict of {population_name: {sample_id: [[allele1, allele2], "
    "...]}} for 1+ populations (diploid genotype calls per sample per "
    "SNP, alleles 0/1/-1(missing), same SNP count within each "
    "population), compute real within-population nucleotide diversity "
    "(pi) for each population via pixy's own vectorized estimator, and "
    "real between-population divergence (dxy) for every population "
    "pair if 2+ populations are given. Never state a pi or dxy value "
    "this tool didn't actually compute.",
    {"populations": dict},
)
async def compute_nucleotide_diversity(args: dict[str, Any]) -> dict[str, Any]:
    populations = args.get("populations")
    if not isinstance(populations, dict) or not populations:
        return {"content": [{"type": "text", "text": "populations must be a non-empty dict of {population_name: {sample_id: [[a1, a2], ...]}}."}]}
    for pop_name, samples in populations.items():
        error = _validate_population(pop_name, samples)
        if error:
            return {"content": [{"type": "text", "text": error}]}

    try:
        from pixy.calc import calc_dxy, calc_pi
    except ImportError:
        return {"content": [{"type": "text", "text": "pixy is not installed in this environment."}]}

    gt_arrays = {pop_name: _build_gt_array(samples) for pop_name, samples in populations.items()}

    lines = ["pixy nucleotide diversity/divergence [pixy:diversity]:"]
    for pop_name, gt in gt_arrays.items():
        pi_result = calc_pi(gt)
        lines.append(f"- pi({pop_name}) = {pi_result.avg_pi} ({pi_result.total_diffs}/{pi_result.total_comps} pairwise differences/comparisons)")

    pop_names = list(gt_arrays.keys())
    for i in range(len(pop_names)):
        for j in range(i + 1, len(pop_names)):
            p1, p2 = pop_names[i], pop_names[j]
            dxy_result = calc_dxy(gt_arrays[p1], gt_arrays[p2])
            lines.append(f"- dxy({p1}, {p2}) = {dxy_result.avg_dxy}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pixy_diversity_mcp_server():
    return create_sdk_mcp_server(name="pixy_diversity", tools=[compute_nucleotide_diversity])
