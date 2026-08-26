"""A real DSSP MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
2, Structural biology cluster) -- subprocess-wrapped `mkdssp` CLI (apt
`dssp` package, see Dockerfile), real per-residue secondary-structure
assignment (alpha helix, beta strand, turn, coil, ...) from a 3D
structure. Fills a real gap: nothing else on this platform assigns
secondary structure from atomic coordinates -- `biopandas_structure`
reports composition/geometry, not per-residue fold classification.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
MAX_RESIDUES_RETURNED = 200


def _run_mkdssp(pdb_path: Path, output_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["mkdssp", str(pdb_path), str(output_path)],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_dssp(text: str) -> list[dict]:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("  #  RESIDUE")), None)
    if start is None:
        return []
    residues = []
    for line in lines[start + 1:]:
        if len(line) < 17 or line[13] == "!":
            continue
        residues.append({"resnum": line[5:10].strip(), "chain": line[11].strip(), "aa": line[13], "ss": line[16] if line[16] != " " else "-"})
    return residues


@tool(
    "assign_secondary_structure",
    "Given a real PDB ID, run DSSP to assign real per-residue secondary "
    "structure (H=alpha helix, E=beta strand, T=turn, G/I=other helix "
    "types, -=coil/loop) from the actual 3D structure. Never state a "
    "residue's secondary structure this tool didn't actually assign.",
    {"pdb_id": str, "chain": str},
)
async def assign_secondary_structure(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = (args.get("pdb_id") or "").strip().upper()
    chain_filter = (args.get("chain") or "").strip().upper()
    if not pdb_id:
        return {"content": [{"type": "text", "text": "pdb_id must not be empty."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdb_path = tmp_path / f"{pdb_id}.pdb"
        pdb_path.write_text(pdb_text)
        output_path = tmp_path / f"{pdb_id}.dssp"
        code, out, err = await asyncio.to_thread(_run_mkdssp, pdb_path, output_path)
        dssp_text = output_path.read_text() if output_path.exists() else ""

    if code != 0 or not dssp_text.strip():
        return {"content": [{"type": "text", "text": f"DSSP failed on PDB {pdb_id}: {err.strip() or 'no output produced'}"}]}

    residues = _parse_dssp(dssp_text)
    if chain_filter:
        residues = [r for r in residues if r["chain"] == chain_filter]
    if not residues:
        return {"content": [{"type": "text", "text": f"DSSP produced no residue assignments for PDB {pdb_id}" + (f" chain {chain_filter}" if chain_filter else "") + "."}]}

    ss_counts: dict[str, int] = {}
    for r in residues:
        ss_counts[r["ss"]] = ss_counts.get(r["ss"], 0) + 1

    lines = [f"DSSP secondary structure for PDB {pdb_id} [dssp:secondary_structure] -- {len(residues)} residue(s):"]
    lines.append("Summary: " + ", ".join(f"{ss}={count}" for ss, count in sorted(ss_counts.items())))
    for r in residues[:MAX_RESIDUES_RETURNED]:
        lines.append(f"- chain {r['chain']} residue {r['resnum']} ({r['aa']}): {r['ss']}")
    if len(residues) > MAX_RESIDUES_RETURNED:
        lines.append(f"... and {len(residues) - MAX_RESIDUES_RETURNED} more residue(s) not shown (see summary above).")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_dssp_secondary_structure_mcp_server():
    return create_sdk_mcp_server(name="dssp_secondary_structure", tools=[assign_secondary_structure])
