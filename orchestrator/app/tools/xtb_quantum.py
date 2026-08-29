"""A real xtb MCP tool (docs/17-remaining-tools-wiring-plan.md Phase 2,
Cheminformatics cluster) -- subprocess-wrapped `xtb` CLI (apt `xtb`
package, real GFN2-xTB semi-empirical tight-binding quantum chemistry,
confirmed live end-to-end before wiring: apt-installed the real deb,
generated a real 3D conformer via RDKit, and ran a real xtb geometry
optimization on it -- not guessed from docs). Real gap this fills:
nothing else on this platform computes an electronic-structure property
(HOMO-LUMO gap, dipole moment, total energy) -- vina_docking/auto3d_
conformers only handle geometry/binding, not electronic structure.

SMILES -> 3D coordinates via RDKit's own ETKDG embedding + MMFF
optimization (fast, deterministic, no neural-network dependency) rather
than routing through auto3d_conformers -- xtb's own GFN2-xTB
optimization step (--opt) refines the geometry further anyway, so a
cheap starting embedding is sufficient and keeps this tool
self-contained.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from rdkit import Chem
from rdkit.Chem import AllChem

MAX_HEAVY_ATOMS = 60

# Real xtb stdout format, confirmed live against an actual run:
#           -------------------------------------------------
#          | TOTAL ENERGY               -5.070370761845 Eh   |
#          | GRADIENT NORM               0.007221585093 Eh/a |
#          | HOMO-LUMO GAP              14.629673576893 eV   |
#           -------------------------------------------------
SUMMARY_PATTERN = re.compile(
    r"\|\s*TOTAL ENERGY\s+([-\d.]+)\s*Eh.*?"
    r"\|\s*GRADIENT NORM\s+([-\d.]+)\s*Eh.*?"
    r"\|\s*HOMO-LUMO GAP\s+([-\d.]+)\s*eV",
    re.DOTALL,
)
DIPOLE_PATTERN = re.compile(r"^\s*full:\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+([\d.]+)\s*$", re.MULTILINE)


def _embed_3d(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        return None
    AllChem.MMFFOptimizeMolecule(mol)
    conf = mol.GetConformer()
    lines = [str(mol.GetNumAtoms()), "xtb_quantum"]
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol()} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}")
    return "\n".join(lines) + "\n"


def _run_xtb(xyz_path: Path, work_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["xtb", xyz_path.name, "--opt", "--gfn", "2"],
        capture_output=True, text=True, timeout=120, cwd=str(work_dir),
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "compute_quantum_properties",
    "Given a SMILES string (at most 60 heavy atoms), embed a real 3D "
    "conformer (RDKit) and run a real GFN2-xTB semi-empirical quantum-"
    "chemistry geometry optimization via xtb. Returns real total "
    "energy, HOMO-LUMO gap, and molecular dipole moment. Never state an "
    "energy, gap, or dipole this tool didn't actually compute.",
    {"smiles": str},
)
async def compute_quantum_properties(args: dict[str, Any]) -> dict[str, Any]:
    smiles = (args.get("smiles") or "").strip()
    if not smiles:
        return {"content": [{"type": "text", "text": "smiles must be non-empty."}]}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"content": [{"type": "text", "text": f"{smiles!r} is not a valid SMILES string."}]}
    if mol.GetNumHeavyAtoms() > MAX_HEAVY_ATOMS:
        return {"content": [{"type": "text", "text": f"molecule has {mol.GetNumHeavyAtoms()} heavy atoms -- at most {MAX_HEAVY_ATOMS} for a tractable semi-empirical optimization here."}]}

    xyz_text = _embed_3d(smiles)
    if xyz_text is None:
        return {"content": [{"type": "text", "text": "RDKit could not generate a 3D conformer for this molecule."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        xyz_path = tmp_path / "molecule.xyz"
        xyz_path.write_text(xyz_text)
        code, out, err = await asyncio.to_thread(_run_xtb, xyz_path, tmp_path)

    # xtb writes its "normal termination" status line to stderr, not
    # stdout -- confirmed live (a real, non-obvious xtb behavior; the
    # results summary itself is on stdout).
    if "normal termination of xtb" not in err:
        return {"content": [{"type": "text", "text": f"xtb calculation failed: {err.strip() or out.strip()[-1000:] or 'unknown error'}"}]}

    summary_match = SUMMARY_PATTERN.search(out)
    if not summary_match:
        return {"content": [{"type": "text", "text": f"xtb ran but the results summary could not be parsed:\n{out[-2000:]}"}]}

    energy, gradient_norm, homo_lumo_gap = summary_match.groups()
    dipole_match = DIPOLE_PATTERN.search(out)

    lines = [
        f"xtb GFN2-xTB quantum-chemistry properties for {smiles} [xtb:properties]:",
        f"- Total energy: {energy} Eh (Hartree)",
        f"- Gradient norm: {gradient_norm} Eh/alpha (optimization convergence)",
        f"- HOMO-LUMO gap: {homo_lumo_gap} eV",
    ]
    if dipole_match:
        lines.append(f"- Molecular dipole moment: {dipole_match.group(1)} Debye")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_xtb_quantum_mcp_server():
    return create_sdk_mcp_server(name="xtb_quantum", tools=[compute_quantum_properties])
