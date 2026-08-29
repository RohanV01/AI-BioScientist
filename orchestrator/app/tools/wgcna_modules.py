"""A real WGCNA MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript` calling
real `WGCNA::blockwiseModules` (CRAN), same pattern as
`cluster_profiler_enrichment`. Real weighted gene co-expression network
construction and module (co-expressed gene cluster) detection from a
caller-supplied expression matrix -- distinct from
`cluster_profiler_enrichment` (enrichment of a known gene list against
an ontology, not co-expression clustering) and from `pycombat_correction`/
`scanpy_clustering` (batch correction / single-cell clustering, not
gene-level co-expression network modules).

Scoped to a caller-supplied expression matrix (not a real DATA-gated
pipeline needing an uploaded raw count file/FASTQ) -- the same
"works from caller-supplied structured data" scoping as
`dnachisel_optimize`/`treemix_population_tree`, per docs/17's own note
that WGCNA is a real next candidate specifically because it doesn't
need file-upload infrastructure this platform doesn't have.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "wgcna_modules.R")
MIN_GENES = 20
MAX_GENES = 500
MIN_SAMPLES = 4
MAX_MODULES_RETURNED = 20


def _run_wgcna(expr_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["Rscript", R_SCRIPT, str(expr_path), str(out_path)], capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "detect_coexpression_modules",
    "Given a dict of {gene_name: [expression_value_per_sample, ...]} "
    "for at least 20 genes and at least 4 samples (same sample count "
    "for every gene), detect real co-expressed gene modules via WGCNA "
    "(weighted gene co-expression network analysis). Returns each "
    "gene's module assignment and each module's size -- module 0 is "
    "reserved for genes that don't fit any module. Never state a "
    "module assignment this tool didn't actually compute.",
    {"expression": dict},
)
async def detect_coexpression_modules(args: dict[str, Any]) -> dict[str, Any]:
    expression = args.get("expression")
    if not isinstance(expression, dict) or len(expression) < MIN_GENES:
        return {"content": [{"type": "text", "text": f"expression must be a dict of at least {MIN_GENES} {{gene_name: [values]}} entries."}]}
    if len(expression) > MAX_GENES:
        return {"content": [{"type": "text", "text": f"at most {MAX_GENES} genes at a time."}]}

    lengths = set()
    for gene, values in expression.items():
        if not isinstance(values, list) or not all(isinstance(v, (int, float)) for v in values):
            return {"content": [{"type": "text", "text": f"gene '{gene}' must map to a list of numeric expression values."}]}
        lengths.add(len(values))
    if len(lengths) != 1:
        return {"content": [{"type": "text", "text": f"all genes must have the same number of sample values -- got lengths {sorted(lengths)}."}]}
    n_samples = lengths.pop()
    if n_samples < MIN_SAMPLES:
        return {"content": [{"type": "text", "text": f"at least {MIN_SAMPLES} samples are needed for correlation-based module detection -- got {n_samples}."}]}

    genes = list(expression.keys())
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        expr_path = tmp_path / "expr.csv"
        out_path = tmp_path / "modules.csv"

        with open(expr_path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["sample"] + genes)
            for sample_idx in range(n_samples):
                writer.writerow([f"sample{sample_idx + 1}"] + [expression[g][sample_idx] for g in genes])

        code, out, err = await asyncio.to_thread(_run_wgcna, expr_path, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"WGCNA module detection failed: {err.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": "WGCNA produced no module assignments."}]}

    modules: dict[str, list[str]] = {}
    for row in rows:
        modules.setdefault(row["module"], []).append(row["gene"])

    lines = [f"WGCNA co-expression modules [wgcna:module] -- {len(modules)} module(s) across {len(rows)} gene(s):"]
    for module_id, module_genes in sorted(modules.items(), key=lambda kv: -len(kv[1]))[:MAX_MODULES_RETURNED]:
        label = "unassigned (module 0)" if module_id == "0" else f"module {module_id}"
        lines.append(f"- {label}: {len(module_genes)} gene(s) -- {', '.join(module_genes[:15])}{'...' if len(module_genes) > 15 else ''}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_wgcna_modules_mcp_server():
    return create_sdk_mcp_server(name="wgcna_modules", tools=[detect_coexpression_modules])
