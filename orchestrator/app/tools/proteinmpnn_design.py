"""A real ProteinMPNN MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1.5, local-GPU tools) -- subprocess-wrapped `proteinmpnn` CLI
(the real `proteinmpnn` PyPI package -- "a slightly cleaned up
installable version of ProteinMPNN", confirmed live before wiring;
`Requires-Python >=3.9,<3.13` is satisfied by this image's Python
3.11). Real inverse protein design: given a 3D backbone (fetched by
real PDB ID, same pattern as `usalign_tmscore.py`), design real amino-
acid sequences predicted to fold into that exact backbone. Fills a
genuine gap -- nothing else on this platform designs a sequence *from*
a structure; `vina_docking` docks a molecule against an existing
protein, a different direction entirely.

Uses the GPU automatically when available (torch ships CUDA support by
default from PyPI, confirmed live -- see docker-compose.gpu.yml), falls
back to CPU otherwise -- correctly slower, not broken, so this tool
works the same way regardless of whether the optional GPU override is
enabled.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
MAX_SEQUENCES = 10
# Real ProteinMPNN FASTA header format and output path (out_folder/
# seqs/<pdb_stem>.fa) -- confirmed live against a real run (1CRN, 2
# designs on this platform's own GPU), not just the package's
# documented example.
DESIGN_HEADER_PATTERN = re.compile(
    r"^>T=[\d.]+, sample=(\d+), score=([\d.]+), global_score=([\d.]+), seq_recovery=([\d.]+)$"
)


def _run_proteinmpnn(pdb_path: Path, out_dir: Path, num_sequences: int, sampling_temp: str) -> tuple[int, str, str]:
    # Real flag names confirmed live: the installed CLI (a wrapper
    # around the package's own argparse definitions) uses hyphens
    # (--out-folder, --pdb-path, ...), not the underscores
    # (--out_folder, --pdb_path) the PyPI README's own usage example
    # shows -- that example is stale/wrong for the actual installed
    # entry point, caught by running this live before wiring rather
    # than trusting the docs alone.
    proc = subprocess.run(
        [
            "proteinmpnn", "--pdb-path", str(pdb_path), "--out-folder", str(out_dir),
            "--num-seq-per-target", str(num_sequences), "--sampling-temp", sampling_temp,
        ],
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "design_sequence_from_structure",
    "Given a real PDB ID and a target number of designs (1-10), run "
    "ProteinMPNN to design real amino-acid sequences predicted to fold "
    "into that exact 3D backbone (inverse protein design). Returns each "
    "designed sequence with its real ProteinMPNN score (lower = higher "
    "confidence) and sequence recovery versus the native sequence. "
    "Never state a designed sequence or score this tool didn't actually "
    "compute.",
    {"pdb_id": str, "num_sequences": int, "sampling_temp": float},
)
async def design_sequence_from_structure(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = (args.get("pdb_id") or "").strip().upper()
    num_sequences = args.get("num_sequences", 4)
    sampling_temp = args.get("sampling_temp", 0.1)
    if not pdb_id:
        return {"content": [{"type": "text", "text": "pdb_id must be non-empty."}]}
    if not isinstance(num_sequences, int) or not (1 <= num_sequences <= MAX_SEQUENCES):
        return {"content": [{"type": "text", "text": f"num_sequences must be an integer between 1 and {MAX_SEQUENCES}."}]}
    if not isinstance(sampling_temp, (int, float)) or not (0.01 <= sampling_temp <= 1.0):
        return {"content": [{"type": "text", "text": "sampling_temp must be between 0.01 and 1.0 (0.1-0.3 is typical; higher = more diverse, less confident)."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdb_path = tmp_path / f"{pdb_id}.pdb"
        pdb_path.write_text(resp.text)
        out_dir = tmp_path / "out"

        code, out, err = await asyncio.to_thread(_run_proteinmpnn, pdb_path, out_dir, num_sequences, str(sampling_temp))
        fasta_path = out_dir / "seqs" / f"{pdb_id}.fa"
        fasta_text = fasta_path.read_text() if fasta_path.exists() else ""

    if not fasta_text.strip():
        return {"content": [{"type": "text", "text": f"ProteinMPNN design failed: {err.strip()[-1500:] or out.strip()[-1500:] or 'unknown error'}"}]}

    entries = fasta_text.strip().split(">")[1:]  # drop leading empty split before the first '>'
    designs = []
    for entry in entries:
        lines = entry.strip().splitlines()
        header, sequence = lines[0], "".join(lines[1:])
        match = DESIGN_HEADER_PATTERN.match(f">{header}")
        if match:
            sample, score, global_score, seq_recovery = match.groups()
            designs.append({"sample": sample, "score": score, "global_score": global_score, "seq_recovery": seq_recovery, "sequence": sequence})

    if not designs:
        return {"content": [{"type": "text", "text": f"ProteinMPNN produced output but no designed sequences could be parsed:\n{fasta_text[:1000]}"}]}

    lines = [f"ProteinMPNN inverse design for {pdb_id} [proteinmpnn:design] -- {len(designs)} designed sequence(s):"]
    for d in designs:
        lines.append(f"- sample {d['sample']}: score={d['score']} (lower=better), seq_recovery={d['seq_recovery']} vs. native\n  {d['sequence']}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_proteinmpnn_design_mcp_server():
    return create_sdk_mcp_server(name="proteinmpnn_design", tools=[design_sequence_from_structure])
