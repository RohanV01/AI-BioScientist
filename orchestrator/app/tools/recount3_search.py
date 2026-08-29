"""A real recount3 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript` calling
real `recount3::available_projects` (Bioconductor), same pattern as
`cluster_profiler_enrichment`/`tcga_clinical`. Real, live catalog of
public RNA-seq studies (SRA, GTEx, TCGA) recount3 has uniformly
reprocessed gene/exon/junction-level counts for -- fetches only the
lightweight study catalog (project ID, organism, sample count), not
any full expression matrix, so this stays a fast metadata lookup, not
a DATA-gated tool.

Real gap this fills: nothing else on this platform helps a researcher
discover which public RNA-seq studies exist and how large they are --
a real first step before any downstream expression analysis (which
does need real file-upload infrastructure this platform doesn't have
yet, per docs/17's own Phase 3 scoping note).
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "recount3_search.R")
VALID_ORGANISMS = {"human", "mouse"}
MAX_PROJECTS_RETURNED = 30


def _run_recount3_query(organism: str, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["Rscript", R_SCRIPT, organism, str(out_path)], capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "search_recount3_studies",
    "Given an organism (human or mouse) and an optional search term, "
    "list real public RNA-seq studies recount3 has uniformly "
    "reprocessed (SRA/GTEx/TCGA), with each study's real project ID, "
    "data source, and sample count -- a discovery step before any "
    "downstream expression analysis. Never state a study's sample "
    "count or source this tool didn't actually retrieve.",
    {"organism": str, "search_term": str},
)
async def search_recount3_studies(args: dict[str, Any]) -> dict[str, Any]:
    organism = (args.get("organism") or "human").strip().lower()
    search_term = (args.get("search_term") or "").strip().lower()
    if organism not in VALID_ORGANISMS:
        return {"content": [{"type": "text", "text": f"organism must be one of {sorted(VALID_ORGANISMS)}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "projects.csv"
        code, out, err = await asyncio.to_thread(_run_recount3_query, organism, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"recount3 project lookup failed: {err.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if search_term:
        rows = [r for r in rows if search_term in str(r.get("project", "")).lower() or search_term in str(r.get("file_source", "")).lower()]
    if not rows:
        return {"content": [{"type": "text", "text": f"No recount3 {organism} studies found" + (f" matching '{search_term}'." if search_term else ".")}]}

    lines = [f"recount3 public RNA-seq study catalog ({organism}) [recount3:project] -- {len(rows)} match(es):"]
    for row in rows[:MAX_PROJECTS_RETURNED]:
        lines.append(f"- {row.get('project', '?')} (source: {row.get('file_source', '?')}, {row.get('n_samples', '?')} samples)")
    if len(rows) > MAX_PROJECTS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_PROJECTS_RETURNED} more not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_recount3_search_mcp_server():
    return create_sdk_mcp_server(name="recount3_search", tools=[search_recount3_studies])
