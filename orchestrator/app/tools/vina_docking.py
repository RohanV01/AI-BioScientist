"""A real AutoDock Vina MCP tool (docs/10-build-plan.md Phase 5's
bio.tools/GitHub-repo triage -- specifically Jupyter_Dock, 286 GitHub
stars, flagged by name as valuable but initially dismissed alongside
the GPU-heavy deep-learning docking tools (DiffDock etc.) without
actually checking what it depends on. Jupyter_Dock itself is just
notebooks; what it actually wraps is AutoDock Vina and LeDock -- both
classical, physics-based, CPU-only docking engines with real Python
bindings (the `vina` package) and no GPU/model-weights dependency at
all. That distinction is why this is buildable now and DiffDock isn't.

This is the single most consequential capability gap this closes: the
platform had ChEMBL (known bioactivity data) and PDB (structure
lookup), but nothing that actually predicts how well a candidate
molecule binds a target structure -- the literal core computational
step of structure-based drug discovery (the report's own flagship 5.5,
"Target-to-Lead Virtual Screening Funnel").

Pipeline: fetch the receptor structure from RCSB -> auto-detect the
binding site from a co-crystallized ligand (or an explicitly given one)
-> RDKit builds a 3D conformer from the candidate's SMILES -> Meeko
preps both receptor and ligand as PDBQT -> Vina docks and scores. All
CPU-bound/blocking work runs via asyncio.to_thread, same pattern as
literature_discovery.py's grep subprocess, so it doesn't block the
orchestrator's event loop.
"""
import asyncio
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

# Real bug found+fixed while building the E2E dock -> analyze-interactions
# chain (this module -> plip_interactions.py, the platform's own core
# workflow): `vina`'s and `openbabel`'s Python bindings are both
# SWIG-generated, and whichever one is imported *first* in a process
# claims the shared libpython SWIG type-registration runtime. Importing
# `vina` first leaves `openbabel` (which PLIP depends on) with a
# corrupted runtime -- not a Python exception, an unrecoverable
# `terminate called after throwing an instance of 'swig::stop_iteration'`
# that aborts the whole orchestrator process the next time PLIP runs,
# however much later that is and regardless of which tool the agent
# calls first. Importing `openbabel` before `vina` here (this module is
# guaranteed to load before any docking call can happen) fixes the
# registration order for the whole process, however the agent later
# invokes plip_interactions.
import openbabel  # noqa: F401 -- import order matters, see comment above; not otherwise used here
from meeko import MoleculePreparation, PDBQTWriterLegacy, Polymer, ResidueChemTemplates
from rdkit import Chem
from rdkit.Chem import AllChem
from vina import Vina

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"

# Waters and common crystallization buffer/cryoprotectant components --
# never a meaningful "binding site reference," so auto-detection skips
# them when picking which co-crystallized hetero group to center on.
_EXCLUDED_HETERO = {"HOH", "SO4", "PO4", "GOL", "EDO", "NA", "CL", "MG", "ZN", "CA", "K"}


def _find_binding_site_center(pdb_text: str, reference_hetero_code: str | None) -> tuple[list[float], str]:
    hetatm_lines = [l for l in pdb_text.splitlines() if l.startswith("HETATM")]
    if reference_hetero_code:
        matches = [l for l in hetatm_lines if l[17:20].strip() == reference_hetero_code]
        if not matches:
            raise ValueError(f"No HETATM records found for residue code {reference_hetero_code!r} in this structure.")
        used_code = reference_hetero_code
    else:
        candidates = [l for l in hetatm_lines if l[17:20].strip() not in _EXCLUDED_HETERO]
        if not candidates:
            raise ValueError("No co-crystallized ligand found to auto-detect a binding site -- pass reference_hetero_code explicitly.")
        used_code = candidates[0][17:20].strip()
        matches = [l for l in candidates if l[17:20].strip() == used_code]

    xs = [float(l[30:38]) for l in matches]
    ys = [float(l[38:46]) for l in matches]
    zs = [float(l[46:54]) for l in matches]
    center = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
    return center, used_code


def _run_docking(pdb_text: str, ligand_smiles: str, reference_hetero_code: str | None, box_size: float, exhaustiveness: int) -> dict:
    center, used_hetero_code = _find_binding_site_center(pdb_text, reference_hetero_code)

    chem_templates = ResidueChemTemplates.create_from_defaults()
    mk_prep = MoleculePreparation()
    polymer = Polymer.from_pdb_string(pdb_text, chem_templates, mk_prep, allow_bad_res=True, default_altloc="A")
    receptor_pdbqt, _ = PDBQTWriterLegacy.write_string_from_polymer(polymer)

    mol = Chem.MolFromSmiles(ligand_smiles)
    if mol is None:
        raise ValueError(f"Could not parse ligand SMILES: {ligand_smiles!r}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        raise ValueError("RDKit could not generate a 3D conformer for this ligand.")
    AllChem.MMFFOptimizeMolecule(mol)
    setups = mk_prep.prepare(mol)
    ligand_pdbqt, _, _ = PDBQTWriterLegacy.write_string(setups[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        receptor_path = Path(tmpdir) / "receptor.pdbqt"
        ligand_path = Path(tmpdir) / "ligand.pdbqt"
        receptor_path.write_text(receptor_pdbqt)
        ligand_path.write_text(ligand_pdbqt)

        v = Vina(sf_name="vina", verbosity=0)
        v.set_receptor(str(receptor_path))
        v.set_ligand_from_file(str(ligand_path))
        v.compute_vina_maps(center=center, box_size=[box_size, box_size, box_size])
        v.dock(exhaustiveness=exhaustiveness, n_poses=5)
        energies = v.energies()

    return {"center": center, "used_hetero_code": used_hetero_code, "energies": energies}


@tool(
    "dock_ligand",
    "Dock a candidate ligand (given as a SMILES string) against a "
    "receptor structure (given as a PDB ID) using AutoDock Vina -- "
    "predicts binding affinity (kcal/mol, more negative is stronger) "
    "and the top 5 poses. The binding site is auto-detected from a "
    "co-crystallized ligand/cofactor in the structure unless "
    "reference_hetero_code names a specific one (get hetero codes from "
    "biopandas_structure.get_structure_composition first). This is a "
    "real physics-based docking search (CPU, ~10-30s), not a "
    "prediction from memory -- never state a binding affinity this "
    "tool didn't return.",
    {"pdb_id": str, "ligand_smiles": str, "reference_hetero_code": str, "box_size": float, "exhaustiveness": int},
)
async def dock_ligand(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = args["pdb_id"].strip().upper()
    box_size = float(args.get("box_size", 20.0))
    exhaustiveness = min(int(args.get("exhaustiveness", 8)), 16)
    reference_hetero_code = (args.get("reference_hetero_code") or "").strip().upper() or None

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    try:
        result = await asyncio.to_thread(
            _run_docking, pdb_text, args["ligand_smiles"], reference_hetero_code, box_size, exhaustiveness
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}]}

    best_energy = result["energies"][0][0]
    center = result["center"]
    lines = [
        f"AutoDock Vina docking against PDB {pdb_id} "
        f"(binding site centered on co-crystallized {result['used_hetero_code']}, "
        f"box {box_size}Å³ at [{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}]):",
        f"- Best predicted binding affinity [vina:{pdb_id}]: {best_energy:.3f} kcal/mol (more negative = stronger predicted binding)",
        f"- Top {len(result['energies'])} poses (kcal/mol): " + ", ".join(f"{e[0]:.3f}" for e in result["energies"]),
        "Note: this is a fast single-run search (not an averaged/replicated screen) -- treat as a first-pass "
        "estimate, not a validated affinity.",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_vina_docking_mcp_server():
    return create_sdk_mcp_server(name="vina_docking", tools=[dock_ligand])
