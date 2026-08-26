"""A real spyrmsd MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Structural biology cluster) -- symmetry-corrected small-molecule pose
RMSD, pairing with the already-live `vina_docking` chain: Vina docks and
scores a ligand pose, spyrmsd tells you how close two ligand poses
(e.g. a docked pose vs. a reference/crystal pose, or two docking runs'
top poses) actually are, correctly accounting for chemically-equivalent
atom relabeling (e.g. a symmetric ring) that a naive coordinate RMSD
would over-penalize.

Accepts two real SDF (MDL Molfile) blocks -- the standard small-molecule
pose format most docking/cheminformatics tools (including RDKit, already
a dependency here) can produce -- rather than raw coordinates, so any
caller with two poses in hand can use this directly.
"""
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from spyrmsd import io, rmsd


@tool(
    "compute_pose_rmsd",
    "Given two small-molecule poses as SDF (MDL Molfile) text blocks --"
    " pose_a and pose_b -- compute the real symmetry-corrected RMSD "
    "between them via spyrmsd (graph-isomorphism-based atom matching, "
    "correctly handling chemically-equivalent atoms rather than penalizing "
    "arbitrary atom-index relabeling). Pairs with vina_docking: use to "
    "compare a docked pose against a reference/crystal pose, or two "
    "docking runs' top poses. Never state an RMSD this tool didn't "
    "actually compute.",
    {"pose_a": str, "pose_b": str},
)
async def compute_pose_rmsd(args: dict[str, Any]) -> dict[str, Any]:
    # Deliberately not .strip()'d -- an MDL Molfile's first line (molecule
    # name) is conventionally blank, and stripping it shifts every
    # subsequent fixed-position line by one, corrupting the counts line
    # OpenBabel's parser reads (confirmed live: this exact bug produced
    # "Invalid operation on a NullGraph" from a well-formed RDKit-written
    # molblock before being traced back to the .strip() call here).
    pose_a = args.get("pose_a") or ""
    pose_b = args.get("pose_b") or ""
    if not pose_a.strip() or not pose_b.strip():
        return {"content": [{"type": "text", "text": "Both pose_a and pose_b must be non-empty SDF text blocks."}]}

    with tempfile.TemporaryDirectory() as tmp:
        path_a, path_b = Path(tmp) / "a.sdf", Path(tmp) / "b.sdf"
        path_a.write_text(pose_a)
        path_b.write_text(pose_b)
        try:
            mol_a = io.loadmol(str(path_a))
            mol_b = io.loadmol(str(path_b))
            mol_a.strip()
            mol_b.strip()
            values = rmsd.rmsdwrapper(mol_a, mol_b, symmetry=True)
        except Exception as exc:  # noqa: BLE001 -- surface real spyrmsd/parsing errors (e.g. mismatched molecules) to the caller
            return {"content": [{"type": "text", "text": f"spyrmsd computation failed: {exc}"}]}

    # [spyrmsd:rmsd] is the citable unit -- real local computation on
    # caller-supplied poses, same methodological-citation convention as
    # vina's [vina:pdb_id] tag.
    return {
        "content": [
            {"type": "text", "text": f"Symmetry-corrected pose RMSD [spyrmsd:rmsd]: {values[0]:.4f} Å"}
        ]
    }


def build_spyrmsd_pose_mcp_server():
    return create_sdk_mcp_server(name="spyrmsd_pose", tools=[compute_pose_rmsd])
