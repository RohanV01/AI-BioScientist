"""Batch virtual screening (docs/12-biotools-triage-shortlist.md's
Cheminformatics section's "pyscreener" entry) -- completes the
drug-discovery pipeline that was stuck at one compound at a time:
ChEMBL (find compounds) -> Vina (dock ONE ligand) -> PLIP (explain ONE
pose). This is the report's own flagship 5.5 ("Target-to-Lead Virtual
Screening Funnel"): rank a shortlist of candidates against a target in
one pass, not one manual dock_ligand call per compound.

Deliberately does NOT install the `pyscreener` package itself: it
pulls in `ray` (a distributed-compute framework -- grpcio, opencensus,
opentelemetry, py-spy, ~15 packages) and `openmm`/`pdbfixer` (a full MD
simulation stack), ~36 packages total for what this platform needs at
chat-tool scale -- a handful of ligands per screen, not a
distributed cluster. Same judgment call as this session's CPU-only-
torch fix for mhcflurry and dropping PEGG for a scikit-learn pin
conflict: match the dependency to the actual computation, not the
library's most general use case.

Instead, this reuses vina_docking.py's own proven, already-live-
verified internals (_find_binding_site_center, _run_docking) directly,
looping over multiple ligands sequentially. Genuinely the same Vina
computation vina_docking.py already does, just batched -- so it reuses
that tool's own [vina:pdb_id] citation tag rather than inventing a new
one; no new RECORD_REF_PATTERNS entry needed.
"""
import asyncio
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

from app.tools.vina_docking import RCSB_DOWNLOAD_URL, _run_docking

MAX_LIGANDS_PER_SCREEN = 10


@tool(
    "batch_dock_ligands",
    "Dock a shortlist of candidate ligands (SMILES strings) against one "
    "receptor structure (PDB ID) using AutoDock Vina, and return them "
    "ranked by predicted binding affinity -- a real virtual screening "
    "pass, not one-at-a-time docking. Same physics-based Vina search as "
    "dock_ligand, just batched (max "
    f"{MAX_LIGANDS_PER_SCREEN} ligands per call, since each dock takes "
    "real wall-clock time). The binding site is auto-detected from a "
    "co-crystallized ligand/cofactor unless reference_hetero_code names "
    "one explicitly. Never state a ranking or affinity this tool didn't "
    "actually return.",
    {"pdb_id": str, "ligand_smiles_list": list, "reference_hetero_code": str, "box_size": float, "exhaustiveness": int},
)
async def batch_dock_ligands(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = args["pdb_id"].strip().upper()
    ligands = [s.strip() for s in args["ligand_smiles_list"] if s.strip()]
    box_size = float(args.get("box_size", 20.0))
    exhaustiveness = min(int(args.get("exhaustiveness", 8)), 16)
    reference_hetero_code = (args.get("reference_hetero_code") or "").strip().upper() or None

    if not ligands:
        return {"content": [{"type": "text", "text": "ligand_smiles_list must contain at least one SMILES string."}]}
    if len(ligands) > MAX_LIGANDS_PER_SCREEN:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Too many ligands ({len(ligands)}) -- max {MAX_LIGANDS_PER_SCREEN} per screening call "
                    "(each dock takes real wall-clock time; split into multiple calls for a larger shortlist).",
                }
            ]
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    results = []
    used_hetero_code = None
    for smiles in ligands:
        try:
            r = await asyncio.to_thread(_run_docking, pdb_text, smiles, reference_hetero_code, box_size, exhaustiveness)
            used_hetero_code = r["used_hetero_code"]
            results.append({"smiles": smiles, "best_energy": r["energies"][0][0], "error": None})
        except ValueError as exc:
            results.append({"smiles": smiles, "best_energy": None, "error": str(exc)})

    ranked = sorted([r for r in results if r["error"] is None], key=lambda r: r["best_energy"])
    failed = [r for r in results if r["error"] is not None]

    lines = [
        f"Virtual screen against PDB {pdb_id} ({len(ligands)} ligand(s)"
        + (f", binding site centered on co-crystallized {used_hetero_code}" if used_hetero_code else "")
        + f") [vina:{pdb_id}]:"
    ]
    for i, r in enumerate(ranked, 1):
        lines.append(f"{i}. {r['smiles']}: {r['best_energy']:.3f} kcal/mol")
    for r in failed:
        lines.append(f"- {r['smiles']}: FAILED -- {r['error']}")
    lines.append(
        "Note: each is a fast single-run search (not averaged/replicated) -- treat as first-pass "
        "ranking, not validated affinities."
    )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_virtual_screening_mcp_server():
    return create_sdk_mcp_server(name="virtual_screening", tools=[batch_dock_ligands])
