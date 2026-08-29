"""A real poolfstat MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2 Population genetics cluster, deferred at the time to the
R/Bioconductor bridge since poolfstat is CRAN-only -- now built as a
real R tool on that bridge, same Rscript-subprocess pattern as
`cluster_profiler_enrichment`). Real Fst (population differentiation)
computation from allele-count data (Pool-Seq or individual genotype
counts), with block-jackknife confidence intervals -- distinct from
`fastani_similarity` (whole-genome sequence identity, not allele-
frequency differentiation) and from `eigensoft_pca`/`admixture_ancestry`
(population structure, not a pairwise differentiation statistic).
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "poolfstat_fst.R")


def _run_poolfstat(counts_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["Rscript", R_SCRIPT, str(counts_path), str(out_path)], capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "compute_pool_fst",
    "Given a dict of {population_name: {snp_id: [ref_allele_count, "
    "total_count]}} for at least 2 populations (the same SNPs in every "
    "population), compute real genome-wide Fst via poolfstat's ANOVA "
    "estimator with block-jackknife confidence intervals -- works "
    "directly from Pool-Seq or individual-genotype allele counts, not "
    "just individual genotypes. Never state an Fst value or confidence "
    "interval this tool didn't actually compute.",
    {"populations": dict},
)
async def compute_pool_fst(args: dict[str, Any]) -> dict[str, Any]:
    populations = args.get("populations")
    if not isinstance(populations, dict) or len(populations) < 2:
        return {"content": [{"type": "text", "text": "populations must be a dict of at least 2 {population_name: {snp_id: [ref_count, total_count]}} entries."}]}

    snp_sets = []
    for pop_name, snps in populations.items():
        if not isinstance(snps, dict) or not snps:
            return {"content": [{"type": "text", "text": f"population '{pop_name}' must map to a non-empty dict of {{snp_id: [ref_count, total_count]}}."}]}
        for snp_id, counts in snps.items():
            if not (isinstance(counts, list) and len(counts) == 2 and all(isinstance(c, int) and c >= 0 for c in counts)):
                return {"content": [{"type": "text", "text": f"population '{pop_name}' SNP '{snp_id}' must be [ref_count, total_count], non-negative ints."}]}
            if counts[0] > counts[1]:
                return {"content": [{"type": "text", "text": f"population '{pop_name}' SNP '{snp_id}': ref_count cannot exceed total_count."}]}
        snp_sets.append(frozenset(snps.keys()))
    if len(set(snp_sets)) != 1:
        return {"content": [{"type": "text", "text": "all populations must list the exact same set of SNP ids."}]}
    if len(snp_sets[0]) < 2:
        return {"content": [{"type": "text", "text": "at least 2 SNPs are needed for a block-jackknife Fst estimate."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        counts_path = tmp_path / "counts.csv"
        out_path = tmp_path / "result.csv"

        with open(counts_path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["population", "snp", "ref_count", "total_count"])
            for pop_name, snps in populations.items():
                for snp_id, (ref_count, total_count) in snps.items():
                    writer.writerow([pop_name, snp_id, ref_count, total_count])

        code, out, err = await asyncio.to_thread(_run_poolfstat, counts_path, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"poolfstat Fst computation failed: {err.strip()[-1500:] or 'unknown error'}"}]}

    rows = {row["metric"]: row["value"] for row in csv.DictReader(io.StringIO(result_text))}
    text = (
        f"poolfstat genome-wide Fst (ANOVA method) [poolfstat:fst]:\n"
        f"- Fst estimate: {rows.get('FST_estimate', '?')}\n"
        f"- Block-jackknife mean: {rows.get('FST_blockjackknife_mean', '?')}, SE: {rows.get('FST_se', '?')}\n"
        f"- 95% CI: [{rows.get('FST_ci_lower', '?')}, {rows.get('FST_ci_upper', '?')}]"
    )
    return {"content": [{"type": "text", "text": text}]}


def build_poolfstat_fst_mcp_server():
    return create_sdk_mcp_server(name="poolfstat_fst", tools=[compute_pool_fst])
