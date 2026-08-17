"""A real PLIP MCP tool (docs/12-biotools-triage-shortlist.md's
Structural biology / docking cluster). PLIP (Protein-Ligand Interaction
Profiler) explains *why* a binding pose looks the way it does -- the
specific hydrogen bonds, hydrophobic contacts, pi-stacking, salt
bridges, halogen bonds, and water bridges holding a ligand in place.
This is the natural follow-up to app/tools/vina_docking.py: Vina scores
a pose, PLIP explains it.

Fetches the structure from RCSB (same pattern as vina_docking.py),
runs a real local PLIP analysis (in-process, via OpenBabel under the
hood), and reports the interaction breakdown for one ligand in the
structure. Real local computation, no external record for the result
itself -- same methodological-citation convention as the other wrapped-
library tools, tagged [plip:pdb_id].
"""
import asyncio
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_PDB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"

# Same convention as vina_docking.py's binding-site auto-detection --
# common crystallographic additives that aren't the biologically
# relevant ligand.
_EXCLUDED_HETERO = {"HOH", "SO4", "PO4", "GOL", "EDO", "NA", "CL", "MG", "ZN", "CA", "K"}


def _run_plip(pdb_text: str, hetero_code: str | None) -> dict:
    from plip.structure.preparation import PDBComplex

    mol = PDBComplex()
    mol.load_pdb(pdb_text, as_string=True)
    if not mol.ligands:
        raise ValueError("No ligands found in this structure -- nothing for PLIP to profile.")

    candidates = [l for l in mol.ligands if l.hetid not in _EXCLUDED_HETERO]
    if not candidates:
        candidates = mol.ligands

    if hetero_code:
        chosen = next((l for l in candidates if l.hetid == hetero_code.upper()), None)
        if chosen is None:
            available = sorted({l.hetid for l in mol.ligands})
            raise ValueError(f"Ligand {hetero_code!r} not found in this structure. Present: {available}")
    else:
        chosen = candidates[0]

    mol.analyze()
    key = f"{chosen.hetid}:{chosen.chain}:{chosen.position}"
    if key not in mol.interaction_sets:
        raise ValueError(f"PLIP produced no interaction set for ligand {key} (binding site may be too small/incomplete).")

    pli = mol.interaction_sets[key]
    return {
        "hetero_code": chosen.hetid,
        "chain": chosen.chain,
        "position": chosen.position,
        "hbonds": list(pli.hbonds_pdon) + list(pli.hbonds_ldon),
        "hydrophobic": list(pli.hydrophobic_contacts),
        "pistacking": list(pli.pistacking),
        "saltbridges": list(pli.saltbridge_pneg) + list(pli.saltbridge_lneg),
        "halogen": list(pli.halogen_bonds),
        "water_bridges": list(pli.water_bridges),
    }


@tool(
    "profile_ligand_interactions",
    "Given a PDB ID (and optionally a specific ligand hetero code if the "
    "structure has more than one), run PLIP to profile the non-covalent "
    "interactions holding that ligand in its binding site: hydrogen bonds, "
    "hydrophobic contacts, pi-stacking, salt bridges, halogen bonds, and "
    "water bridges. Explains *why* a binding pose looks the way it does -- "
    "pair with vina_docking's dock_ligand for a docked pose's interactions. "
    "Never state an interaction (residue, distance) this tool didn't "
    "actually return.",
    {"pdb_id": str, "hetero_code": str},
)
async def profile_ligand_interactions(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = args["pdb_id"].strip().upper()
    hetero_code = (args.get("hetero_code") or "").strip().upper() or None

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(RCSB_PDB_URL.format(pdb_id=pdb_id))
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    try:
        result = await asyncio.to_thread(_run_plip, pdb_text, hetero_code)
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}]}

    # [plip:pdb_id] is the citable unit -- real local computation, same
    # methodological-citation convention as scikit-bio/cobra/vina.
    lines = [
        f"PDB {pdb_id} -- PLIP interaction profile for ligand {result['hetero_code']} "
        f"(chain {result['chain']}, position {result['position']}) [plip:{pdb_id}]:"
    ]

    if result["hbonds"]:
        lines.append(f"Hydrogen bonds ({len(result['hbonds'])}):")
        for h in result["hbonds"]:
            lines.append(f"  - {h.restype}{h.resnr} ({h.reschain}): {h.distance_ad:.2f}A, angle {h.angle:.0f} deg")
    if result["hydrophobic"]:
        lines.append(f"Hydrophobic contacts ({len(result['hydrophobic'])}):")
        for hc in result["hydrophobic"]:
            lines.append(f"  - {hc.restype}{hc.resnr} ({hc.reschain}): {hc.distance:.2f}A")
    if result["pistacking"]:
        lines.append(f"Pi-stacking interactions ({len(result['pistacking'])}):")
        for ps in result["pistacking"]:
            lines.append(f"  - {ps.restype}{ps.resnr} ({ps.reschain}): {ps.distance:.2f}A, type {ps.type}")
    if result["saltbridges"]:
        lines.append(f"Salt bridges ({len(result['saltbridges'])}):")
        for sb in result["saltbridges"]:
            lines.append(f"  - {sb.restype}{sb.resnr} ({sb.reschain}): {sb.distance:.2f}A")
    if result["halogen"]:
        lines.append(f"Halogen bonds ({len(result['halogen'])}):")
        for hx in result["halogen"]:
            lines.append(f"  - {hx.restype}{hx.resnr} ({hx.reschain}): {hx.distance:.2f}A")
    if result["water_bridges"]:
        lines.append(f"Water bridges ({len(result['water_bridges'])}):")
        for wb in result["water_bridges"]:
            lines.append(f"  - {wb.restype}{wb.resnr} ({wb.reschain}): {wb.distance_aw:.2f}A to water")

    if len(lines) == 1:
        lines.append("No non-covalent interactions detected above PLIP's default thresholds.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_plip_interactions_mcp_server():
    return create_sdk_mcp_server(name="plip_interactions", tools=[profile_ligand_interactions])
