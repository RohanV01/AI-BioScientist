"""A real TCGAbiolinks MCP tool (docs/17-remaining-tools-wiring-
plan.md Phase 3, R/Bioconductor bridge) -- subprocess-wrapped
`Rscript` calling real `TCGAbiolinks::GDCquery_clinic` (Bioconductor),
same pattern as `cluster_profiler_enrichment`. Real, live clinical
data for a TCGA cancer project, fetched directly from the GDC REST API
(api.gdc.cancer.gov) -- no BAM/expression-matrix downloads, so this
isn't DATA-gated the way most of the remaining R-bridge candidates are
(see docs/17's Phase 3 scoping note).

Distinct from `cbioportal_mutations` (mutation frequency across public
studies): this is patient-level clinical annotation (diagnosis, stage,
vital status, demographics) for a named TCGA project, a different
question entirely.
"""
import asyncio
import csv
import io
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "tcga_clinical.R")
MAX_PATIENTS_RETURNED = 20
# Real TCGA project ID format, e.g. TCGA-BRCA, TCGA-LUAD -- confirmed
# against GDC's own project-id convention.
PROJECT_ID_PATTERN = re.compile(r"^TCGA-[A-Z]{2,6}$")
DISPLAY_FIELDS = ["submitter_id", "vital_status", "age_at_diagnosis", "primary_diagnosis", "ajcc_pathologic_stage", "gender"]


def _run_tcga_query(project: str, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["Rscript", R_SCRIPT, project, str(out_path)], capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "get_tcga_clinical_data",
    "Given a TCGA project ID (e.g. TCGA-BRCA, TCGA-LUAD, TCGA-COAD -- "
    "the format is always TCGA-<tumor type code>), fetch real patient "
    "clinical data (diagnosis, stage, vital status, demographics) for "
    "that project directly from the GDC (Genomic Data Commons) REST "
    "API via TCGAbiolinks. Never state a clinical fact this tool "
    "didn't actually retrieve.",
    {"project": str},
)
async def get_tcga_clinical_data(args: dict[str, Any]) -> dict[str, Any]:
    project = (args.get("project") or "").strip().upper()
    if not PROJECT_ID_PATTERN.match(project):
        return {"content": [{"type": "text", "text": "project must look like TCGA-<code>, e.g. TCGA-BRCA, TCGA-LUAD."}]}

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "clinical.csv"
        code, out, err = await asyncio.to_thread(_run_tcga_query, project, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"TCGAbiolinks query failed: {err.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if rows and "error" in rows[0] and len(rows[0]) == 1:
        return {"content": [{"type": "text", "text": f"GDC query for '{project}' failed: {rows[0]['error']}"}]}
    if not rows:
        return {"content": [{"type": "text", "text": f"No clinical records found for project '{project}'."}]}

    lines = [f"TCGAbiolinks clinical data for {project} [tcgabiolinks:patient] -- {len(rows)} patient(s):"]
    for row in rows[:MAX_PATIENTS_RETURNED]:
        fields = "; ".join(f"{f}={row[f]}" for f in DISPLAY_FIELDS if f in row and row[f])
        lines.append(f"- {fields}")
    if len(rows) > MAX_PATIENTS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_PATIENTS_RETURNED} more patient(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_tcga_clinical_mcp_server():
    return create_sdk_mcp_server(name="tcga_clinical", tools=[get_tcga_clinical_data])
