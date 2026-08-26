"""A real Auto3D MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Cheminformatics cluster) -- SMILES -> real 3D conformers via a neural
network potential (AIMNET), closing the gap between ChEMBL's 2D SMILES
output and vina_docking's 3D-structure input requirement.

Confirmed live before wiring (2026-08-26): Auto3D's torch backend
attempts a JIT C++ compile step (torch.compile/inductor) that fails with
"cannot find -ltorch" when the process's working/install path contains a
space -- a real, environment-specific bug, not an Auto3D bug per se, but
guarded against here defensively (TORCHDYNAMO_DISABLE) since it's cheap
insurance and this platform's own deployment path is not guaranteed to
be space-free everywhere it might run.
"""
import os
from typing import Any

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

from claude_agent_sdk import create_sdk_mcp_server, tool
from rdkit import Chem


@tool(
    "generate_3d_conformer",
    "Given a SMILES string, generate a real low-energy 3D conformer via "
    "Auto3D (RDKit isomer enumeration + AIMNET neural-network-potential "
    "geometry optimization) -- closes the gap between a 2D SMILES (e.g. "
    "from chembl.py/pubchem.py) and vina_docking's 3D-structure "
    "requirement. Returns the conformer as a real MDL Molfile (SDF) "
    "block. Never state a conformer/energy this tool didn't actually "
    "compute.",
    {"smiles": str},
)
async def generate_3d_conformer(args: dict[str, Any]) -> dict[str, Any]:
    smiles = (args.get("smiles") or "").strip()
    if not smiles:
        return {"content": [{"type": "text", "text": "smiles must be non-empty."}]}
    if Chem.MolFromSmiles(smiles) is None:
        return {"content": [{"type": "text", "text": f"{smiles!r} is not a valid SMILES string."}]}

    import asyncio

    def _run() -> str:
        from Auto3D.auto3D import Auto3DOptions, smiles2mols

        options = Auto3DOptions(k=1, use_gpu=False, optimizing_engine="AIMNET")
        mols = smiles2mols([smiles], options)
        if not mols:
            return ""
        return Chem.MolToMolBlock(mols[0])

    try:
        molblock = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001 -- surface real Auto3D/AIMNET errors to the caller
        return {"content": [{"type": "text", "text": f"Auto3D conformer generation failed: {exc}"}]}

    if not molblock:
        return {"content": [{"type": "text", "text": f"Auto3D produced no valid conformer for {smiles!r}."}]}

    # [auto3d:conformer] is the citable methodological tag -- real local
    # computation, same convention as vina's [vina:pdb_id] tag.
    return {
        "content": [
            {"type": "text", "text": f"Auto3D 3D conformer [auto3d:conformer] for {smiles}:\n{molblock}"}
        ]
    }


def build_auto3d_conformers_mcp_server():
    return create_sdk_mcp_server(name="auto3d_conformers", tools=[generate_3d_conformer])
