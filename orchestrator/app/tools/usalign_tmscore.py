"""A real US-align MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Structural biology cluster) -- subprocess-wrapped `USalign`
binary (compiled from source at Docker build time, see Dockerfile; not
apt-installable, same class as diamond_search.py/foldseek_search.py
just via compilation instead of a prebuilt release), real pairwise
structural alignment producing TM-score -- the field-standard,
sequence-independent structural similarity metric.

Distinct from foldseek_search (fast heuristic search across many
targets): this is the rigorous, exact pairwise structural superposition
between exactly two structures, with the real TM-score/RMSD a
researcher would cite -- the right tool when precision on one specific
pair matters more than search speed across many candidates, same
relationship as emboss_water vs. blast_search for sequences.
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
TM_SCORE_PATTERN = re.compile(r"TM-score=\s*([\d.]+).*?Chain_([12])", re.DOTALL)
RMSD_PATTERN = re.compile(r"RMSD=\s*([\d.]+)")
ALIGNED_LENGTH_PATTERN = re.compile(r"Aligned length=\s*(\d+)")


def _run_usalign(struct_a_path: Path, struct_b_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["USalign", str(struct_a_path), str(struct_b_path)],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "usalign_tmscore",
    "Given two real PDB IDs, run US-align to compute the real pairwise "
    "structural alignment and TM-score (sequence-independent structural "
    "similarity, 0-1, >0.5 generally indicates the same fold) between "
    "them -- the rigorous, precise pairwise comparison, distinct from "
    "foldseek_search's fast search across many targets. Never state a "
    "TM-score/RMSD this tool didn't actually compute.",
    {"pdb_id_a": str, "pdb_id_b": str},
)
async def usalign_tmscore(args: dict[str, Any]) -> dict[str, Any]:
    pdb_a = (args.get("pdb_id_a") or "").strip().upper()
    pdb_b = (args.get("pdb_id_b") or "").strip().upper()
    if not pdb_a or not pdb_b:
        return {"content": [{"type": "text", "text": "pdb_id_a and pdb_id_b must both be non-empty."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp_a = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_a}.pdb")
        if resp_a.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_a!r}."}]}
        resp_a.raise_for_status()
        resp_b = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_b}.pdb")
        if resp_b.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_b!r}."}]}
        resp_b.raise_for_status()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        struct_a_path = tmp_path / f"{pdb_a}.pdb"
        struct_b_path = tmp_path / f"{pdb_b}.pdb"
        struct_a_path.write_text(resp_a.text)
        struct_b_path.write_text(resp_b.text)
        code, out, err = await asyncio.to_thread(_run_usalign, struct_a_path, struct_b_path)

    if code != 0 or not out.strip():
        return {"content": [{"type": "text", "text": f"US-align failed: {err.strip() or 'no output produced'}"}]}

    tm_scores = TM_SCORE_PATTERN.findall(out)
    rmsd_match = RMSD_PATTERN.search(out)
    aligned_match = ALIGNED_LENGTH_PATTERN.search(out)
    if not tm_scores:
        return {"content": [{"type": "text", "text": "US-align produced output but its TM-score could not be parsed."}]}

    lines = [f"US-align structural alignment [usalign:tmscore] -- {pdb_a} vs {pdb_b}:"]
    for score, chain in tm_scores:
        lines.append(f"- TM-score normalized by chain {chain} length: {score}")
    if rmsd_match:
        lines.append(f"- RMSD: {rmsd_match.group(1)} Angstrom")
    if aligned_match:
        lines.append(f"- Aligned length: {aligned_match.group(1)} residues")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_usalign_tmscore_mcp_server():
    return create_sdk_mcp_server(name="usalign_tmscore", tools=[usalign_tmscore])
