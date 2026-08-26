"""A real egglib MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Population genetics cluster) -- real local population-genetics
diversity statistics (segregating sites, nucleotide diversity, Watterson's
theta, Tajima's D) via the egglib package, computed on caller-supplied
aligned sequences. Natural downstream step from the already-live `msa`
tool (align_sequences) -- MAFFT produces the aligned input this tool
consumes directly.

Fills a real gap: nothing in this platform's roster before this could
compute classic population-genetics summary statistics from a set of
aligned sequences (as distinct from msprime's forward *simulation* of
coalescent diversity, or scikit_bio's microbiome alpha-diversity metrics
-- a different domain, taxon-abundance-table-based).
"""
from typing import Any

import egglib
from claude_agent_sdk import create_sdk_mcp_server, tool

STATS = ["S", "Pi", "thetaW", "D"]
STAT_LABELS = {
    "S": "segregating sites (count of variable positions)",
    "Pi": "nucleotide diversity (pi, average pairwise differences)",
    "thetaW": "Watterson's theta (expected diversity under neutral evolution)",
    "D": "Tajima's D (positive: balancing selection/pop. contraction signal; negative: purifying selection/pop. expansion signal)",
}


@tool(
    "compute_diversity_statistics",
    "Given a dict of {sequence_name: aligned_dna_sequence} (all sequences "
    "must be the same length -- already aligned, e.g. via the msa tool's "
    "align_sequences output), compute real population-genetics diversity "
    "statistics via egglib: segregating sites (S), nucleotide diversity "
    "(Pi), Watterson's theta, and Tajima's D. Requires at least 3 "
    "sequences. Never state a statistic this tool didn't actually "
    "compute.",
    {"sequences": dict},
)
async def compute_diversity_statistics(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or len(sequences) < 3:
        return {"content": [{"type": "text", "text": "sequences must be a dict of at least 3 {name: aligned_sequence} pairs."}]}
    lengths = {len(v) for v in sequences.values()}
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"All sequences must be the same length (already aligned) -- got lengths {sorted(lengths)}."}]}

    try:
        aln = egglib.Align.create(
            [(name, seq.upper(), []) for name, seq in sequences.items()], alphabet=egglib.alphabets.DNA
        )
        cs = egglib.stats.ComputeStats()
        cs.add_stats(*STATS)
        stats = cs.process_align(aln)
    except Exception as exc:  # noqa: BLE001 -- surface real egglib errors (e.g. non-ACGT characters) to the caller
        return {"content": [{"type": "text", "text": f"egglib computation failed: {exc}"}]}

    # [egglib:stat] is the citable unit -- real local computation, same
    # methodological-citation convention as scikit-bio/msprime.
    lines = [f"Population-genetics diversity statistics for {len(sequences)} aligned sequences:"]
    for name in STATS:
        value = stats.get(name)
        if value is None:
            lines.append(f"- {STAT_LABELS[name]} [egglib:{name}]: undefined (no valid sites)")
        else:
            lines.append(f"- {STAT_LABELS[name]} [egglib:{name}]: {value:.6g}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_egglib_popgen_mcp_server():
    return create_sdk_mcp_server(name="egglib_popgen", tools=[compute_diversity_statistics])
