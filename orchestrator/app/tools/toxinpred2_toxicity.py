"""A real ToxinPred2 MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2 Cheminformatics cluster -- re-investigated after the earlier
live-confirmed rejection, per explicit direction to fix the important
ones rather than skip them). ToxinPred2 v1.0/v1.1 both crash
unconditionally on any real input via `CM.to_csv("Sequence_1", ...,
sep="\\n")` -- Python's `csv` module has always rejected `"\\n"` as a
delimiter. Confirmed live this single line is the only actual blocker
for Model 1 (the RF-based model, no BLAST DB needed) -- the malformed
file it writes is only ever *read* by Model 2's BLAST/MERCI hybrid
path, never by Model 1's own prediction path. Fixed with a real,
minimal, documented source patch in the Dockerfile (`sed`-replacing
that one `sep="\\n"` with `sep=","`, a valid single-column-safe
delimiter) rather than forking the package -- confirmed live
end-to-end after patching: real toxin/non-toxin predictions with real
ML scores produced.
"""
import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_SEQUENCES = 50


def _run_toxinpred2(fasta_path: Path, out_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["toxinpred2", "-i", str(fasta_path), "-o", str(out_path), "-m", "1", "-d", "2"],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "predict_peptide_toxicity",
    "Given a dict of {sequence_name: peptide_or_protein_sequence} (at "
    "most 50 sequences), predict whether each is toxic via ToxinPred2's "
    "amino-acid-composition-based random forest model. Returns each "
    "sequence's toxin/non-toxin call and ML score. Never state a "
    "toxicity call or score this tool didn't actually predict.",
    {"sequences": dict},
)
async def predict_peptide_toxicity(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or not sequences:
        return {"content": [{"type": "text", "text": "sequences must be a non-empty dict of {name: sequence}."}]}
    if len(sequences) > MAX_SEQUENCES:
        return {"content": [{"type": "text", "text": f"at most {MAX_SEQUENCES} sequences at a time."}]}
    valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
    for name, seq in sequences.items():
        if not isinstance(seq, str) or not seq or not set(seq.upper()) <= valid_aa:
            return {"content": [{"type": "text", "text": f"sequence '{name}' must be a non-empty string of standard amino acid letters."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fasta_path = tmp_path / "input.fasta"
        fasta_path.write_text("".join(f">{name}\n{seq.upper()}\n" for name, seq in sequences.items()))
        out_path = tmp_path / "output.csv"

        code, out, err = await asyncio.to_thread(_run_toxinpred2, fasta_path, out_path)
        result_text = out_path.read_text() if out_path.exists() else ""

    if not result_text.strip():
        return {"content": [{"type": "text", "text": f"ToxinPred2 failed: {err.strip()[-1000:] or out.strip()[-1000:] or 'unknown error'}"}]}

    rows = list(csv.DictReader(io.StringIO(result_text)))
    if not rows:
        return {"content": [{"type": "text", "text": "ToxinPred2 produced no predictions."}]}

    lines = ["ToxinPred2 peptide toxicity prediction (RF, amino-acid composition) [toxinpred2:prediction]:"]
    for row in rows:
        seq_id = row.get("ID", "?")
        prediction = row.get("Prediction", "?")
        score = row.get("ML_Score", row.get("ML Score", "?"))
        lines.append(f"- {seq_id}: {prediction} (ML score {score})")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_toxinpred2_toxicity_mcp_server():
    return create_sdk_mcp_server(name="toxinpred2_toxicity", tools=[predict_peptide_toxicity])
