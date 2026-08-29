"""A real clusterProfiler MCP tool (docs/17-remaining-tools-wiring-
plan.md Phase 3, the R/Bioconductor bridge's first tool) -- subprocess-
wrapped `Rscript` calling real clusterProfiler::enrichGO (Bioconductor).

**Architecture decision (Phase 3, made here, not a default):** an
`Rscript` subprocess bridge, not `rpy2`. rpy2 gives tighter Python<->R
type marshaling, but is a real, well-known source of production
fragility -- version-sensitive against both the R and Python it's
built against, R_HOME/ABI mismatches across environments, and no
graceful failure mode (a broken binding can crash the whole process,
not just one tool call). An `Rscript` subprocess is exactly the same
shape as every CLONE-tier tool already in this codebase (tempfile in,
subprocess out, parse stdout/output file) -- no new failure mode, no
new dependency class, degrades the same way any other subprocess tool
does. `CONTRIBUTING.md`'s existing tool recipe holds unchanged. Real R
script lives at `r_scripts/cluster_profiler_enrich.R`, not inlined
here, so it can be read/tested independently of this wrapper.

Distinct from the already-live `gene_set_enrichment`/
`gprofiler_enrichment` (both real, but different engines/statistics)
-- this is clusterProfiler specifically, the most widely-cited GO/KEGG
enrichment tool in the Bioconductor ecosystem, useful as a comparison
point against those.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "cluster_profiler_enrich.R")
VALID_ORGANISMS = {"human", "mouse"}
VALID_ONTOLOGIES = {"BP", "MF", "CC", "ALL"}
MAX_TERMS_RETURNED = 20


def _run_cluster_profiler(genes_path: Path, organism: str, ontology: str, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["Rscript", R_SCRIPT, str(genes_path), organism, ontology, str(out_path)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "enrich_gene_ontology_clusterprofiler",
    "Given a list of gene symbols, an organism (human or mouse), and a "
    "GO ontology (BP, MF, CC, or ALL), run real GO enrichment analysis "
    "via clusterProfiler (Bioconductor's most widely-used enrichment "
    "tool) with Benjamini-Hochberg FDR correction. Returns enriched GO "
    "terms with their adjusted p-values and matching genes. Never state "
    "an enriched term or p-value this tool didn't actually compute.",
    {"genes": list, "organism": str, "ontology": str},
)
async def enrich_gene_ontology_clusterprofiler(args: dict[str, Any]) -> dict[str, Any]:
    genes = args.get("genes")
    organism = args.get("organism") or "human"
    ontology = args.get("ontology") or "BP"
    if not isinstance(genes, list) or len(genes) < 3:
        return {"content": [{"type": "text", "text": "genes must be a list of at least 3 gene symbols."}]}
    if organism not in VALID_ORGANISMS:
        return {"content": [{"type": "text", "text": f"organism must be one of {sorted(VALID_ORGANISMS)}."}]}
    if ontology not in VALID_ONTOLOGIES:
        return {"content": [{"type": "text", "text": f"ontology must be one of {sorted(VALID_ONTOLOGIES)}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        genes_path = tmp_path / "genes.txt"
        genes_path.write_text("\n".join(str(g).strip() for g in genes if str(g).strip()))
        out_path = tmp_path / "result.csv"

        code, out, err = await asyncio.to_thread(_run_cluster_profiler, genes_path, organism, ontology, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0:
        return {"content": [{"type": "text", "text": f"clusterProfiler failed: {err.strip()[-1500:] or 'unknown error'}"}]}
    if not result_text.strip():
        return {"content": [{"type": "text", "text": "clusterProfiler produced no output."}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": f"clusterProfiler found no significantly enriched {ontology} terms (FDR < 0.05) for this gene list."}]}

    lines = [f"clusterProfiler GO enrichment ({ontology}, {organism}) [clusterprofiler:term] -- {len(rows)} significant term(s):"]
    for row in rows[:MAX_TERMS_RETURNED]:
        go_id = row.get("ID", "?")
        desc = row.get("Description", "")
        padj = row.get("p.adjust", "?")
        gene_ratio = row.get("GeneRatio", "?")
        lines.append(f"- {go_id} ({desc}): adjusted p={padj}, gene ratio={gene_ratio}")
    if len(rows) > MAX_TERMS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_TERMS_RETURNED} more term(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_cluster_profiler_enrichment_mcp_server():
    return create_sdk_mcp_server(name="cluster_profiler_enrichment", tools=[enrich_gene_ontology_clusterprofiler])
