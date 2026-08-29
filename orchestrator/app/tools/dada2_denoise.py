"""A real dada2 MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
3, R/Bioconductor bridge) -- subprocess-wrapped `Rscript` running
dada2's own documented tutorial pipeline verbatim (filterAndTrim ->
learnErrors -> dada -> makeSequenceTable -> removeBimeraDenovo), same
pattern as `cluster_profiler_enrichment`. Real amplicon-sequencing
denoising: given a researcher's own uploaded raw FASTQ reads, infers
real Amplicon Sequence Variants (ASVs) and their abundances -- the
first of the file-upload-gated R-bridge tools, unblocked by the real
Mattermost file-attachment pipeline (app/file_uploads.py).

Requires a file the researcher actually uploaded (see
`list_uploaded_files`) -- never accepts inline sequence data as a
substitute, since dada2's whole value is learning a real per-run error
model from real raw reads, not something a few example sequences can
stand in for.
"""
import asyncio
import csv
import io
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.experiment_context import uploads_dir

R_SCRIPT = str(Path(__file__).parent / "r_scripts" / "dada2_denoise.R")
MAX_VARIANTS_RETURNED = 30


def _run_dada2(fastq_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(["Rscript", R_SCRIPT, str(fastq_path), str(out_path)], capture_output=True, text=True, timeout=600)
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "dada2_denoise_amplicons",
    "Given the filename of a real uploaded FASTQ file (see "
    "list_uploaded_files -- must have format `fastq`), run dada2 to "
    "denoise the raw reads into real Amplicon Sequence Variants (ASVs) "
    "with their real abundances. Genuinely slow (real error-model "
    "learning across the whole file, not a lookup) -- do not abandon a "
    "call early on this basis alone. Never state an ASV sequence or "
    "abundance this tool didn't actually compute.",
    {"filename": str},
)
async def dada2_denoise_amplicons(args: dict[str, Any]) -> dict[str, Any]:
    filename = (args.get("filename") or "").strip()
    updir = uploads_dir()
    if not filename or updir is None:
        return {"content": [{"type": "text", "text": "filename must be non-empty, and this experiment must have an uploaded file."}]}
    fastq_path = updir / filename
    if not fastq_path.is_file():
        return {"content": [{"type": "text", "text": f"No uploaded file named {filename!r} in this experiment -- call list_uploaded_files first."}]}

    out_path = updir / f"{filename}.dada2_result.csv"
    code, out, err = await asyncio.to_thread(_run_dada2, fastq_path, out_path)
    result_text = out_path.read_text() if out_path.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"dada2 denoising failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": f"dada2 found no amplicon sequence variants in {filename}."}]}

    lines = [f"dada2 amplicon denoising for {filename} [dada2:asv] -- {len(rows)} real ASV(s):"]
    for row in rows[:MAX_VARIANTS_RETURNED]:
        seq = row.get("sequence_variant", "?")
        abundance = row.get("abundance", "?")
        lines.append(f"- abundance={abundance}: {seq}")
    if len(rows) > MAX_VARIANTS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_VARIANTS_RETURNED} more ASV(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_dada2_denoise_mcp_server():
    return create_sdk_mcp_server(name="dada2_denoise", tools=[dada2_denoise_amplicons])
