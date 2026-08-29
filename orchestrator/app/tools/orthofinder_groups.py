"""A real OrthoFinder MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Phylogenetics cluster) -- subprocess-wrapped `orthofinder`
CLI. Not apt-installable or on PyPI (confirmed live before assuming
either); the real distribution is the project's own self-contained
GitHub release tarball (`OrthoFinder.tar.gz`), which bundles its own
diamond/mcl/fastme binaries -- installed via a Dockerfile download
step, not apt/pip.

Real gap this fills: comparative-genomics orthology inference across
*multiple* species' full proteomes (orthogroups, i.e. sets of genes
descended from a single gene in the last common ancestor) -- distinct
from `diamond_search`/`blast_search` (pairwise sequence similarity
only, no orthogroup/duplication-aware clustering) and from
`phylogenetics`/`fasttree_tree` (build a tree from an alignment the
caller already has, not discover orthology relationships from raw
proteomes in the first place).

Genuinely slow for anything beyond a toy input (full DIAMOND
all-vs-all + MCL clustering + gene-tree inference per orthogroup) --
timeout set generously rather than rejecting slow-but-correct runs,
per explicit user direction that latency is not a rejection reason.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_SPECIES = 10
MAX_SEQUENCES_PER_SPECIES = 200
RUN_TIMEOUT_SECONDS = 3600
MAX_ORTHOGROUPS_RETURNED = 30


def _run_orthofinder(fasta_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["orthofinder", "-f", str(fasta_dir), "-t", "4"],
        capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _find_orthogroups_tsv(fasta_dir: Path) -> Path | None:
    results_root = fasta_dir / "OrthoFinder"
    if not results_root.is_dir():
        return None
    # OrthoFinder names its results dir Results_<Month><Day> and appends
    # a counter (_1, _2, ...) on repeated runs against the same input
    # dir -- take the most recently created one rather than assuming a
    # fixed name.
    candidates = sorted(results_root.glob("Results_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        tsv = candidate / "Orthogroups" / "Orthogroups.tsv"
        if tsv.exists():
            return tsv
    return None


@tool(
    "find_orthogroups",
    "Given a dict of {species_name: {protein_id: sequence}} for 2-10 "
    "species (whole or partial proteomes, amino acid sequences), run "
    "OrthoFinder to identify real orthogroups -- sets of genes across "
    "the given species descended from a single ancestral gene, "
    "accounting for gene duplication. Returns each orthogroup's member "
    "genes per species. This is a real, potentially slow (minutes to "
    "over an hour for larger inputs) full comparative-genomics run, not "
    "a quick lookup -- do not abandon a call early on this basis alone. "
    "Never state an orthogroup membership this tool didn't actually "
    "compute.",
    {"species": dict},
)
async def find_orthogroups(args: dict[str, Any]) -> dict[str, Any]:
    species = args.get("species")
    if not isinstance(species, dict) or len(species) < 2:
        return {"content": [{"type": "text", "text": "species must be a dict of at least 2 {species_name: {protein_id: sequence}} entries."}]}
    if len(species) > MAX_SPECIES:
        return {"content": [{"type": "text", "text": f"at most {MAX_SPECIES} species at a time -- OrthoFinder's all-vs-all comparison grows quadratically."}]}
    for name, proteins in species.items():
        if not isinstance(proteins, dict) or not proteins:
            return {"content": [{"type": "text", "text": f"species '{name}' must map to a non-empty dict of {{protein_id: sequence}}."}]}
        if len(proteins) > MAX_SEQUENCES_PER_SPECIES:
            return {"content": [{"type": "text", "text": f"species '{name}' has {len(proteins)} proteins -- at most {MAX_SEQUENCES_PER_SPECIES} per species."}]}

    with tempfile.TemporaryDirectory() as tmp:
        fasta_dir = Path(tmp) / "proteomes"
        fasta_dir.mkdir()
        for name, proteins in species.items():
            safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
            fasta_path = fasta_dir / f"{safe_name}.fasta"
            fasta_path.write_text("".join(f">{pid}\n{seq}\n" for pid, seq in proteins.items()))

        code, out, err = await asyncio.to_thread(_run_orthofinder, fasta_dir)
        tsv_path = _find_orthogroups_tsv(fasta_dir)
        tsv_text = tsv_path.read_text() if tsv_path else ""

    if not tsv_text.strip():
        return {"content": [{"type": "text", "text": f"OrthoFinder failed to produce orthogroups: {err.strip() or out.strip() or 'unknown error'}"}]}

    rows = [r.split("\t") for r in tsv_text.strip().splitlines()]
    header, data_rows = rows[0], rows[1:]
    species_columns = header[1:]

    lines = [f"OrthoFinder orthogroups [orthofinder:orthogroup] -- {len(data_rows)} orthogroup(s) across {len(species_columns)} species:"]
    for row in data_rows[:MAX_ORTHOGROUPS_RETURNED]:
        orthogroup_id = row[0]
        members = {species_columns[i]: row[i + 1] for i in range(len(species_columns)) if i + 1 < len(row) and row[i + 1].strip()}
        member_str = "; ".join(f"{sp}: {genes}" for sp, genes in members.items())
        lines.append(f"- {orthogroup_id}: {member_str}")
    if len(data_rows) > MAX_ORTHOGROUPS_RETURNED:
        lines.append(f"... and {len(data_rows) - MAX_ORTHOGROUPS_RETURNED} more orthogroup(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_orthofinder_groups_mcp_server():
    return create_sdk_mcp_server(name="orthofinder_groups", tools=[find_orthogroups])
