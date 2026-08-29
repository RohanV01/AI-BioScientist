"""A real BioTransformer MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Cheminformatics cluster) -- subprocess-wrapped BioTransformer
3.0.0 (real Java tool, github.com/Wishartlab-openscience/Biotransformer;
not distributed as a prebuilt jar release -- compiled from source via
Maven at Docker build time, real recipe confirmed against the project's
own `install-via-maven.sh` script rather than guessed -- see
Dockerfile). Real small-molecule metabolism prediction (Djoumbou Feunang
et al. 2019): given a drug/xenobiotic SMILES, predicts real metabolite
structures from CYP450 oxidation, Phase II conjugation, and gut-
microbial biotransformation rules. Fills a real gap -- nothing else on
this platform predicts what a compound turns into inside the body;
chembl.py/pubchem.py/openfda.py only cover the parent compound as
administered.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

BIOTRANSFORMER_HOME = "/opt/biotransformer"
BIOTRANSFORMER_JAR = f"{BIOTRANSFORMER_HOME}/biotransformer.jar"
VALID_BTYPES = {"ecbased", "cyp450", "phaseII", "hgut", "superbio", "allHuman", "envimicro"}
MAX_ROWS_RETURNED = 20


def _run_biotransformer(smiles: str, btype: str, steps: int, out_csv: Path) -> tuple[int, str, str]:
    # cwd must be BIOTRANSFORMER_HOME, not a tempdir -- config.json's
    # database/supportfiles paths are relative to the process's working
    # directory, not the jar's location (confirmed against config.json's
    # own "database/HUMAN" style relative paths). out_csv is still an
    # absolute path under the caller's tempdir, so the output itself
    # doesn't pollute BIOTRANSFORMER_HOME.
    proc = subprocess.run(
        ["java", "-jar", BIOTRANSFORMER_JAR, "-k", "pred", "-b", btype, "-ismi", smiles, "-ocsv", str(out_csv), "-s", str(steps)],
        capture_output=True, text=True, timeout=180, cwd=BIOTRANSFORMER_HOME,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "predict_metabolites",
    "Given a drug/xenobiotic SMILES string, predict its real metabolites "
    "via BioTransformer 3.0 (CYP450 oxidation, Phase II conjugation, "
    "and/or human gut microbial biotransformation rules, depending on "
    "biotransformer_type). biotransformer_type must be one of: "
    "ecbased, cyp450, phaseII, hgut, superbio, allHuman, envimicro "
    "(default allHuman -- broadest human coverage). Returns each "
    "predicted metabolite. Never state a metabolite structure this tool "
    "didn't actually predict.",
    {"smiles": str, "biotransformer_type": str, "steps": int},
)
async def predict_metabolites(args: dict[str, Any]) -> dict[str, Any]:
    smiles = (args.get("smiles") or "").strip()
    if not smiles:
        return {"content": [{"type": "text", "text": "smiles must be non-empty."}]}
    btype = args.get("biotransformer_type") or "allHuman"
    if btype not in VALID_BTYPES:
        return {"content": [{"type": "text", "text": f"biotransformer_type must be one of {sorted(VALID_BTYPES)}."}]}
    steps = args.get("steps", 1)
    if not isinstance(steps, int) or not (1 <= steps <= 4):
        return {"content": [{"type": "text", "text": "steps must be an integer between 1 and 4 -- each added step multiplies the search space."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_csv = tmp_path / "metabolites.csv"
        code, out, err = await asyncio.to_thread(_run_biotransformer, smiles, btype, steps, out_csv)
        csv_text = out_csv.read_text() if out_csv.exists() else ""

    if not csv_text.strip():
        return {"content": [{"type": "text", "text": f"BioTransformer produced no output: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        return {"content": [{"type": "text", "text": f"BioTransformer found no predicted metabolites for {smiles} ({btype}, {steps} step(s))."}]}

    lines = [f"BioTransformer {btype} metabolite prediction ({steps} step(s)) [biotransformer:metabolite] -- {len(rows)} metabolite(s):"]
    for row in rows[:MAX_ROWS_RETURNED]:
        # Report every column BioTransformer actually returned rather than
        # assuming a fixed schema -- its CSV columns aren't documented in
        # its own README and weren't verified against a live run (Maven
        # build not testable in this environment), so this stays correct
        # regardless of the exact real column names.
        fields = "; ".join(f"{k}={v}" for k, v in row.items() if v)
        lines.append(f"- {fields}")
    if len(rows) > MAX_ROWS_RETURNED:
        lines.append(f"... and {len(rows) - MAX_ROWS_RETURNED} more metabolite(s) not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_biotransformer_metabolism_mcp_server():
    return create_sdk_mcp_server(name="biotransformer_metabolism", tools=[predict_metabolites])
