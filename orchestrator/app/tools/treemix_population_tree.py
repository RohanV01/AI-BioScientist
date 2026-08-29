"""A real TreeMix MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Population genetics cluster) -- subprocess-wrapped `treemix`
CLI, compiled from source at Docker build time (not apt/pip
installable; real recipe confirmed against the project's own bioconda
build script rather than guessed -- see Dockerfile). Real population-
split/migration-graph inference (Pickrell & Pritchard 2012) from
per-population allele counts -- distinct from
`phylogenetics`/`fasttree_tree` (build a tree from a sequence
alignment) and `astral_pro_tree` (species tree from gene trees): this
infers population history, including admixture/migration edges, from
allele-frequency drift alone.
"""
import asyncio
import gzip
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_MIGRATION_EDGES = 5


def _run_treemix(infile: Path, outstem: Path, migration_edges: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["treemix", "-i", str(infile), "-o", str(outstem), "-k", "1", "-m", str(migration_edges)],
        capture_output=True, text=True, timeout=180,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "build_population_tree",
    "Given a dict of {population_name: [[allele1_count, allele2_count], "
    "...]} for at least 3 populations (per-SNP allele counts, same "
    "number of SNPs and SNP order across all populations), run TreeMix "
    "to infer a real population tree describing splits (and, if "
    "migration_edges > 0, admixture/migration events) driven by "
    "allele-frequency drift. Returns the real inferred tree. Never "
    "state a population relationship this tool didn't actually infer.",
    {"populations": dict, "migration_edges": int},
)
async def build_population_tree(args: dict[str, Any]) -> dict[str, Any]:
    populations = args.get("populations")
    migration_edges = args.get("migration_edges", 0)
    if not isinstance(populations, dict) or len(populations) < 3:
        return {"content": [{"type": "text", "text": "populations must be a dict of at least 3 {population_name: [[count1, count2], ...]} entries."}]}
    if not isinstance(migration_edges, int) or not (0 <= migration_edges <= MAX_MIGRATION_EDGES):
        return {"content": [{"type": "text", "text": f"migration_edges must be an integer between 0 and {MAX_MIGRATION_EDGES}."}]}

    lengths = set()
    for pop_name, counts in populations.items():
        if not isinstance(counts, list) or not counts:
            return {"content": [{"type": "text", "text": f"population '{pop_name}' must map to a non-empty list of [count1, count2] pairs."}]}
        for pair in counts:
            if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(c, int) and c >= 0 for c in pair)):
                return {"content": [{"type": "text", "text": f"population '{pop_name}' has a malformed allele-count pair -- each SNP must be [count1, count2] non-negative ints."}]}
        lengths.add(len(counts))
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"all populations must list the same number of SNPs -- got lengths {sorted(lengths)}."}]}

    pop_names = list(populations.keys())
    n_snps = lengths.pop()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        infile = tmp_path / "input.gz"
        outstem = tmp_path / "output"

        # Real TreeMix input format, confirmed against its own
        # CountData.cpp parser: header row of population names, one row
        # per SNP with each population's "count1,count2" field, gzipped.
        with gzip.open(infile, "wt") as fh:
            fh.write(" ".join(pop_names) + "\n")
            for snp_idx in range(n_snps):
                fh.write(" ".join(f"{populations[p][snp_idx][0]},{populations[p][snp_idx][1]}" for p in pop_names) + "\n")

        code, out, err = await asyncio.to_thread(_run_treemix, infile, outstem, migration_edges)
        treeout_path = Path(f"{outstem}.treeout.gz")
        tree_text = ""
        if treeout_path.exists():
            with gzip.open(treeout_path, "rt") as fh:
                tree_text = fh.readline().strip()

    if not tree_text:
        return {"content": [{"type": "text", "text": f"TreeMix failed to produce a tree: {err.strip() or out.strip() or 'unknown error'}"}]}

    lines = [
        f"TreeMix population tree for {len(pop_names)} populations, {migration_edges} migration edge(s) [treemix:tree]:",
        tree_text,
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_treemix_population_tree_mcp_server():
    return create_sdk_mcp_server(name="treemix_population_tree", tools=[build_population_tree])
