"""A real msprime MCP tool (docs/10-build-plan.md Phase 5's bio.tools +
GitHub-repo triage, wave 1). msprime is the standard coalescent
simulator for population genetics -- simulating expected genetic
diversity under a demographic model is the standard way to build null
expectations before interpreting real variant data (this platform's
gnomAD/ClinVar tools give observed variation; nothing before this gave
expected variation under a model to compare against).

Same shape as scikit_bio.py/cobra_fba.py: real local computation (the
msprime + tskit C libraries, installed into the orchestrator's own
venv), no network dependency, no external record to cite.
"""
from typing import Any

import msprime
from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "simulate_coalescent_diversity",
    "Simulate a coalescent population-genetic model with msprime "
    "(neutral, single panmictic population, optional recombination) and "
    "report expected diversity statistics -- nucleotide diversity (pi), "
    "number of segregating sites, and Tajima's D. Useful as a null-model "
    "baseline to compare against observed variation. Never state a "
    "statistic this tool didn't actually compute.",
    {
        "sample_size": int, "sequence_length": int, "population_size": int,
        "mutation_rate": float, "recombination_rate": float, "random_seed": int,
    },
)
async def simulate_coalescent_diversity(args: dict[str, Any]) -> dict[str, Any]:
    # `or <default>` treats an explicit 0/0.0 as "not given" (falsy) and
    # silently replaces it with the default instead of validating it --
    # e.g. an explicit population_size=0 would silently become 10_000
    # rather than hitting the "must be a positive integer" check below,
    # and mutation_rate=0.0 (a legitimate "no new mutations" request)
    # would silently become 1e-8. `is not None` preserves an explicit 0.
    sample_size = int(args["sample_size"]) if args.get("sample_size") is not None else 20
    sequence_length = int(args["sequence_length"]) if args.get("sequence_length") is not None else 10_000
    population_size = int(args["population_size"]) if args.get("population_size") is not None else 10_000
    mutation_rate = float(args["mutation_rate"]) if args.get("mutation_rate") is not None else 1e-8
    recombination_rate = float(args["recombination_rate"]) if args.get("recombination_rate") is not None else 0.0
    random_seed = args.get("random_seed")

    if sample_size < 2 or sample_size > 1000:
        return {"content": [{"type": "text", "text": "sample_size must be between 2 and 1000 (haploid sample count)."}]}
    if sequence_length < 100 or sequence_length > 10_000_000:
        return {"content": [{"type": "text", "text": "sequence_length must be between 100bp and 10,000,000bp."}]}
    if population_size < 1:
        return {"content": [{"type": "text", "text": "population_size must be a positive integer (diploid effective size)."}]}

    ts = msprime.sim_ancestry(
        samples=sample_size, sequence_length=sequence_length,
        population_size=population_size, recombination_rate=recombination_rate,
        random_seed=random_seed,
    )
    mts = msprime.sim_mutations(ts, rate=mutation_rate, random_seed=random_seed)

    diversity = mts.diversity()
    # span_normalise=False for the raw site count -- the default
    # (span_normalise=True) divides by sequence_length, which for a typical
    # simulation is a small fraction (e.g. 77 sites / 50,000bp = 0.00154)
    # and silently rounds to "0.0" under any reasonable display precision,
    # making a real result look like zero segregating sites were found.
    seg_sites = mts.segregating_sites(span_normalise=False)
    tajimas_d = mts.Tajimas_D()

    # [msprime:simulation] is the citable unit -- same methodological-
    # citation convention as scikit-bio/cobra/vina (real local
    # computation, not an external database record).
    lines = [
        f"Coalescent simulation [msprime:simulation] "
        f"(n={sample_size} haploid samples, L={sequence_length}bp, "
        f"Ne={population_size}, mu={mutation_rate}, r={recombination_rate}):",
        f"- Nucleotide diversity (pi): {diversity:.6f}",
        f"- Segregating sites: {seg_sites:.0f}",
        # Tajima's D is mathematically undefined (nan) when there are no
        # segregating sites -- e.g. mutation_rate=0 -- since its formula
        # divides by a variance term that's zero in that case. Report that
        # plainly instead of a bare "nan", which reads as a rendering bug.
        f"- Tajima's D: {tajimas_d:.4f}" if tajimas_d == tajimas_d else "- Tajima's D: undefined (no segregating sites)",
        f"- Trees in ancestral recombination graph: {ts.num_trees}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_msprime_mcp_server():
    return create_sdk_mcp_server(name="msprime", tools=[simulate_coalescent_diversity])
