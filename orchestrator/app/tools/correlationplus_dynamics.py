"""A real correlationplus MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Structural biology cluster) -- dynamical/allosteric residue
correlation from a single static structure via an Elastic Network Model
(ANM), no MD trajectory needed. Fills a real gap: nothing else in this
platform's roster can answer "which residues move together" (a real
allostery/flexibility signal) from just a deposited structure --
`vina_docking` scores a fixed pose, `plip_interactions` explains its
contacts, but neither says anything about the protein's own intrinsic
dynamics.

Fetches the structure by real PDB ID (RCSB, free/unauthenticated) rather
than accepting arbitrary caller-supplied coordinates, consistent with
every other external-API tool in the roster.

Confirmed live before wiring (2026-08-26): correlationplus's PyPI
metadata pins `numpy<2.0`, but the package is pure Python -- it imports
and computes correctly against `numpy>=2` (unlike DockQ, which has a
genuinely numpy-ABI-bound compiled extension and was rejected for this
same platform for exactly that reason, see docs/17). Verified, not
assumed.
"""
import tempfile
from pathlib import Path
from typing import Any

import correlationplus.calculate as cp_calc
import httpx
import prody
from claude_agent_sdk import create_sdk_mcp_server, tool

PDB_DOWNLOAD_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"


@tool(
    "compute_residue_correlations",
    "Given a real PDB ID and a chain ID, fetch the structure and compute "
    "real dynamical cross-correlations between CA atoms via an Elastic "
    "Network Model (ANM, no MD trajectory needed) -- which residues move "
    "together (correlation near +1), which move oppositely (near -1), "
    "and which are dynamically independent (near 0). Returns the most "
    "strongly correlated and anti-correlated residue pairs. Use for "
    "allostery/flexibility questions a fixed docked pose can't answer. "
    "Never state a correlation value this tool didn't actually compute.",
    {"pdb_id": str, "chain_id": str},
)
async def compute_residue_correlations(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = (args.get("pdb_id") or "").strip().upper()
    chain_id = (args.get("chain_id") or "A").strip().upper()
    if not pdb_id:
        return {"content": [{"type": "text", "text": "pdb_id must be non-empty."}]}

    with tempfile.TemporaryDirectory() as tmp:
        pdb_path = Path(tmp) / f"{pdb_id}.pdb"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(PDB_DOWNLOAD_URL.format(pdb_id=pdb_id))
            if resp.status_code == 404:
                return {"content": [{"type": "text", "text": f"No PDB entry found for pdb_id {pdb_id!r}."}]}
            resp.raise_for_status()
            pdb_path.write_text(resp.text)

        try:
            structure = prody.parsePDB(str(pdb_path), subset="ca", chain=chain_id)
            if structure is None or structure.numAtoms() < 3:
                return {"content": [{"type": "text", "text": f"Chain {chain_id!r} not found (or too few CA atoms) in PDB {pdb_id}."}]}
            nmodes = min(50, structure.numAtoms() - 1)
            cc_matrix = cp_calc.calcENMnDCC(structure, cut_off=15, method="ANM", nmodes=nmodes, saveMatrix=False)
        except Exception as exc:  # noqa: BLE001 -- surface real ProDy/correlationplus errors to the caller
            return {"content": [{"type": "text", "text": f"Correlation computation failed: {exc}"}]}

    resnums = structure.getResnums()
    n = len(resnums)
    pairs = [
        (resnums[i], resnums[j], cc_matrix[i, j])
        for i in range(n) for j in range(i + 1, n)
    ]
    pairs.sort(key=lambda p: p[2])
    most_anti = pairs[:5]
    most_corr = sorted(pairs, key=lambda p: -p[2])[:5]

    # [correlationplus:anm] is the citable methodological tag -- real
    # local computation via an Elastic Network Model, same convention as
    # scikit-bio/cobra/vina.
    lines = [
        f"Dynamical cross-correlation (ANM, {nmodes} modes) for PDB {pdb_id} chain {chain_id} "
        f"({n} residues) [correlationplus:anm]:",
        "Most correlated pairs (move together):",
    ]
    lines += [f"- residue {a} <-> residue {b}: {c:.3f}" for a, b, c in most_corr]
    lines.append("Most anti-correlated pairs (move oppositely):")
    lines += [f"- residue {a} <-> residue {b}: {c:.3f}" for a, b, c in most_anti]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_correlationplus_dynamics_mcp_server():
    return create_sdk_mcp_server(name="correlationplus_dynamics", tools=[compute_residue_correlations])
