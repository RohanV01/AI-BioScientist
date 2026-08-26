"""A real LightDock MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Cheminformatics cluster) -- real protein-protein docking via
the LightDock glowworm swarm optimization algorithm, subprocess-wrapped
(same pattern as msa.py's MAFFT and phylogenetics.py's PhyKIT). Fills a
real gap: `vina_docking` only handles small-molecule ligands against a
protein receptor -- nothing in this platform's roster can dock two
protein chains against each other.

Fetches one real PDB structure and splits it into receptor/ligand chains
server-side (same "real PDB ID in, real computation out" pattern as
vina_docking.py), then runs LightDock's real 3-stage CLI pipeline
(lightdock3_setup.py -> lightdock3.py -> lgd_rank.py) in a temp
directory. Confirmed live before wiring (2026-08-26) that a small
swarm/step count completes well within a chat-tool-scale timeout (5
swarms x 20 glowworms x 10 steps: under 90s against a real 124-residue
chain pair) while still producing real, ranked docking poses -- not a
guess at reasonable defaults.
"""
import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
LD_BIN_DIR = str(Path(sys.executable).parent)
DEFAULT_SWARMS = 5
DEFAULT_GLOWWORMS = 20
DEFAULT_STEPS = 10


def _split_chains(pdb_text: str, receptor_chain: str, ligand_chain: str) -> tuple[str, str]:
    receptor_lines, ligand_lines = [], []
    for line in pdb_text.splitlines(keepends=True):
        if line.startswith(("ATOM", "TER")) and len(line) > 21:
            chain = line[21]
            if chain == receptor_chain:
                receptor_lines.append(line)
            elif chain == ligand_chain:
                ligand_lines.append(line)
    receptor_lines.append("END\n")
    ligand_lines.append("END\n")
    return "".join(receptor_lines), "".join(ligand_lines)


def _run_lightdock(receptor_pdb: str, ligand_pdb: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        receptor_path, ligand_path = tmp_path / "receptor.pdb", tmp_path / "ligand.pdb"
        receptor_path.write_text(receptor_pdb)
        ligand_path.write_text(ligand_pdb)

        setup = subprocess.run(
            [f"{LD_BIN_DIR}/lightdock3_setup.py", str(receptor_path), str(ligand_path), "-s", str(DEFAULT_SWARMS), "-g", str(DEFAULT_GLOWWORMS)],
            cwd=tmp, capture_output=True, text=True, timeout=60,
        )
        if setup.returncode != 0:
            raise RuntimeError(f"lightdock3_setup.py failed: {setup.stderr.strip() or setup.stdout.strip()}")

        sim = subprocess.run(
            [f"{LD_BIN_DIR}/lightdock3.py", "setup.json", str(DEFAULT_STEPS)],
            cwd=tmp, capture_output=True, text=True, timeout=120,
        )
        if sim.returncode != 0:
            raise RuntimeError(f"lightdock3.py simulation failed: {sim.stderr.strip() or sim.stdout.strip()}")

        rank = subprocess.run(
            [f"{LD_BIN_DIR}/lgd_rank.py", str(DEFAULT_SWARMS), str(DEFAULT_STEPS), "--ignore_clusters"],
            cwd=tmp, capture_output=True, text=True, timeout=30,
        )
        if rank.returncode != 0:
            raise RuntimeError(f"lgd_rank.py failed: {rank.stderr.strip() or rank.stdout.strip()}")

        rank_file = tmp_path / "rank_by_scoring.list"
        if not rank_file.exists():
            raise RuntimeError("lgd_rank.py produced no rank_by_scoring.list output.")
        return rank_file.read_text()


@tool(
    "dock_protein_protein",
    "Given a real PDB ID and two chain IDs within it (receptor_chain, "
    "ligand_chain), run real protein-protein docking via LightDock's "
    "glowworm swarm optimization -- complements vina_docking, which "
    "only handles small-molecule ligands, not protein-protein docking. "
    f"Uses a small, fast configuration ({DEFAULT_SWARMS} swarms x "
    f"{DEFAULT_GLOWWORMS} glowworms x {DEFAULT_STEPS} steps) suitable "
    "for a real-time chat response, not an exhaustive production run -- "
    "treat results as a first-pass pose ranking. Returns the top-ranked "
    "poses by LightDock scoring function (more negative = better). "
    "Never state a score/pose this tool didn't actually compute.",
    {"pdb_id": str, "receptor_chain": str, "ligand_chain": str, "max_results": int},
)
async def dock_protein_protein(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = (args.get("pdb_id") or "").strip().upper()
    receptor_chain = (args.get("receptor_chain") or "").strip().upper()
    ligand_chain = (args.get("ligand_chain") or "").strip().upper()
    max_results = min(int(args.get("max_results", 5)), 20)
    if not pdb_id or not receptor_chain or not ligand_chain:
        return {"content": [{"type": "text", "text": "pdb_id, receptor_chain, and ligand_chain must all be non-empty."}]}
    if receptor_chain == ligand_chain:
        return {"content": [{"type": "text", "text": "receptor_chain and ligand_chain must be different."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    receptor_pdb, ligand_pdb = _split_chains(pdb_text, receptor_chain, ligand_chain)
    if receptor_pdb.strip() == "END" or ligand_pdb.strip() == "END":
        return {"content": [{"type": "text", "text": f"Chain {receptor_chain!r} or {ligand_chain!r} not found in PDB {pdb_id}."}]}

    try:
        rank_text = await asyncio.to_thread(_run_lightdock, receptor_pdb, ligand_pdb)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"content": [{"type": "text", "text": f"LightDock docking failed: {exc}"}]}

    data_lines = [l for l in rank_text.splitlines() if l.strip() and not l.startswith("Swarm")]
    if not data_lines:
        return {"content": [{"type": "text", "text": "LightDock produced no ranked poses."}]}

    # [lightdock:pdb_id] is the citable methodological tag; PDB ID itself
    # is separately caught by the existing "PDB {}" pattern.
    lines = [f"LightDock protein-protein docking: PDB {pdb_id} chain {receptor_chain} (receptor) vs chain {ligand_chain} (ligand) [lightdock:{pdb_id}] -- top {min(len(data_lines), max_results)} poses:"]
    for row in data_lines[:max_results]:
        parts = row.split()
        swarm, glowworm, score = parts[0], parts[1], parts[-1]
        lines.append(f"- swarm {swarm}, glowworm {glowworm}: LightDock score {score}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_lightdock_docking_mcp_server():
    return create_sdk_mcp_server(name="lightdock_docking", tools=[dock_protein_protein])
