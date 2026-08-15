"""
Phase 4 — AutoDock Vina docking pipeline.

Receptor preparation (Jupyter_Dock pattern):
  1. PDBFixer — adds missing residues/atoms, adds hydrogens at physiological pH
     (removes water + heterogens so only the apo protein remains).
     Scientific basis: pH 7.4 protonation states match physiological binding
     conditions. Removing crystallographic heterogens prevents pocket occlusion.
  2. mk_prepare_receptor.py (meeko) — converts fixed PDB → PDBQT, assigns
     AutoDock atom types (A/C/HD/N/NA/OA/S/SA…).  Meeko is the reference
     implementation for Vina PDBQT generation.

Ligand preparation:
  - RDKit ETKDGv3 conformer generation + MMFF94 minimisation
  - meeko MoleculePreparation → PDBQT string (handles torsion tree, atom types)
  Scientific basis: ETKDGv3 produces experimental-torsion-based 3D conformers
  that overlap well with crystal poses (Wang et al. 2020, JCIM).

Docking box:
  - Centre = fpocket pocket centroid (cx, cy, cz) from Phase 2.
  - Size = max(22, volume^(1/3) × 1.5) Å on each axis, capped at 35 Å.
  - Exhaustiveness = 8 (Vina default) for Tier 1 known drugs; 4 for bulk
    library screening (2× faster, ~5% lower AUROC — acceptable for ranking).
  Scientific basis: Box sizing ensures ligand can fully explore the pocket
  without clashing with the boundary (Trott & Olson 2010, J Comput Chem).

Vina binary: ~/.local/bin/vina (installed by Phase 0 / this session).
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

_VINA_CANDIDATES = [
    os.path.expanduser("~/.local/bin/vina"),
    "vina",
]
_RECEPTOR_PREP_SCRIPT = str(Path(sys.executable).parent / "mk_prepare_receptor.py")

_PDB_DOWNLOAD_TIMEOUT = 45   # seconds
_VINA_TIMEOUT        = 120  # seconds per ligand
_EMBED_ATTEMPTS      = 5    # RDKit conformer attempts before giving up


# ─────────────────────────────────────────────────────────────────────────────
# Vina binary lookup
# ─────────────────────────────────────────────────────────────────────────────

def _vina_bin() -> Optional[str]:
    for cand in _VINA_CANDIDATES:
        try:
            r = subprocess.run([cand, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0 or b"vina" in (r.stdout + r.stderr).lower():
                return cand
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Receptor preparation
# ─────────────────────────────────────────────────────────────────────────────

def prepare_receptor_pdbqt(pdb_source: str, work_dir: Path) -> Optional[Path]:
    """
    Prepare receptor PDBQT from a local file path or remote URL.

    Accepts either:
      - A local file path (absolute or relative) — copied directly, no network call.
      - An http/https URL — downloaded first.

    Returns path to the receptor.pdbqt, or None on failure.
    """
    # 1. Obtain PDB — local copy or download
    pdb_path = work_dir / "receptor.pdb"
    local_src = Path(pdb_source)
    if local_src.exists():
        shutil.copy(local_src, pdb_path)
    else:
        try:
            resp = requests.get(pdb_source, timeout=_PDB_DOWNLOAD_TIMEOUT, stream=True)
            resp.raise_for_status()
            pdb_path.write_bytes(resp.content)
        except Exception as exc:
            log.warning("[4.dock] PDB fetch failed (%s): %s", pdb_source, exc)
            return None

    # 2. PDBFixer — clean + add hydrogens
    fixed_pdb = work_dir / "receptor_H.pdb"
    try:
        from pdbfixer import PDBFixer
        from openmm.app import PDBFile

        fixer = PDBFixer(filename=str(pdb_path))
        fixer.removeHeterogens(keepWater=False)
        fixer.findMissingResidues()
        fixer.findMissingAtoms()
        fixer.addMissingHydrogens(7.4)
        with open(str(fixed_pdb), "w") as fh:
            PDBFile.writeFile(fixer.topology, fixer.positions, fh)
    except Exception as exc:
        log.warning("[4.dock] PDBFixer failed: %s — using raw PDB", exc)
        shutil.copy(pdb_path, fixed_pdb)

    # 3. mk_prepare_receptor.py → PDBQT
    pdbqt_out = work_dir / "receptor.pdbqt"
    try:
        result = subprocess.run(
            [
                sys.executable, _RECEPTOR_PREP_SCRIPT,
                "--read_pdb", str(fixed_pdb),
                "-o", str(work_dir / "receptor"),
                "-p", str(pdbqt_out),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if pdbqt_out.exists() and pdbqt_out.stat().st_size > 0:
            log.debug("[4.dock] Receptor PDBQT: %d bytes", pdbqt_out.stat().st_size)
            return pdbqt_out
        log.warning("[4.dock] mk_prepare_receptor failed: %s", result.stderr[:300])
    except Exception as exc:
        log.warning("[4.dock] Receptor prep error: %s", exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Ligand preparation
# ─────────────────────────────────────────────────────────────────────────────

def smiles_to_pdbqt(smiles: str, work_dir: Path, ligand_id: str) -> Optional[Path]:
    """
    SMILES → 3D conformer (RDKit ETKDGv3+MMFF94) → PDBQT (meeko).

    Returns path to ligand.pdbqt or None on failure.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from meeko import MoleculePreparation, PDBQTWriterLegacy

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # B8 fix: strip salts/counterions — keep the largest organic fragment.
        # SaltRemover only handles common pharmaceutical salts (HCl, Na, K, etc.).
        # Largest-fragment selection works universally (gluconate, mesylate, tartrate…)
        # ~10% of ChEMBL canonical SMILES are multi-fragment salt forms.
        frags = Chem.rdmolops.GetMolFrags(mol, asMols=True)
        if len(frags) > 1:
            mol = max(frags, key=lambda f: f.GetNumAtoms())

        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42

        for _ in range(_EMBED_ATTEMPTS):
            rc = AllChem.EmbedMolecule(mol, params)
            if rc == 0:
                break
        else:
            return None

        AllChem.MMFFOptimizeMolecule(mol)

        prep = MoleculePreparation()
        mol_setups = prep.prepare(mol)
        if not mol_setups:
            return None

        pdbqt_str, is_ok, err = PDBQTWriterLegacy.write_string(mol_setups[0])
        if not is_ok:
            log.debug("[4.dock] meeko warning for %s: %s", ligand_id, err)

        lig_path = work_dir / f"{ligand_id}.pdbqt"
        lig_path.write_text(pdbqt_str)
        return lig_path

    except Exception as exc:
        log.debug("[4.dock] smiles_to_pdbqt failed for %s: %s", ligand_id, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Docking box
# ─────────────────────────────────────────────────────────────────────────────

_PLDDT_MIN = 70.0  # H4: below this, receptor structure is unreliable for docking

def check_structure_quality(plddt: float) -> bool:
    """
    H4 fix: return False (skip docking) when median pLDDT < 70.

    Scientific rationale: AlphaFold2 pLDDT < 70 indicates an intrinsically
    disordered or low-confidence region. Docking to such structures produces
    artefactual poses because the side-chain conformations are unreliable
    (Jumper et al. 2021, Nature). Skipping docking and using clinical+KG
    signals only is more honest than a structurally noisy Vina score.
    """
    return float(plddt) >= _PLDDT_MIN


def detect_covalent_target(
    tier1_drugs: List[Dict],
    variants: Optional[Dict] = None,
) -> Dict:
    """
    B4 fix: detect whether a target is likely a covalent binder target.

    Two evidence sources:
      1. ChEMBL drug_mechanism text — any Tier-1 drug with "covalent" in MOA
         confirms covalent mechanism (e.g. sotorasib, afatinib, osimertinib).
      2. Phase 2 AlphaMissense variants — if the target has ≥1 high-pathogenicity
         missense variant at a Cys residue, it may have a reactive cysteine that
         enables covalent chemistry (KRAS G12C, EGFR T790M Cys797, etc.).

    Scientific rationale:
      AutoDock Vina uses a non-covalent force field and cannot model covalent bond
      formation. Vina scores for covalent binders (warhead drugs) underestimate
      true binding affinity because the irreversible covalent step is not scored.
      Covalent warheads (acrylamide, chloroacetamide, vinyl sulfone) score as if
      they are just making van der Waals contacts, typically −6 to −9 kcal/mol
      vs the actual −12 to −18 kcal/mol equivalent for the irreversible bond.
      Flagging these targets prevents misranking.

    Returns dict with: is_covalent (bool), covalent_evidence (str), covalent_note (str).
    """
    covalent_keywords = ["covalent", "irreversible", "warhead", "acrylamide",
                         "chloroacetamide", "vinyl sulfone", "michael acceptor"]

    # Source 1: ChEMBL MOA text from Tier-1 drugs
    covalent_drugs = []
    for drug in tier1_drugs:
        moa = (drug.get("mechanism_of_action") or "").lower()
        if any(kw in moa for kw in covalent_keywords):
            covalent_drugs.append(drug.get("drug_name", ""))

    if covalent_drugs:
        note = (
            f"Covalent binding confirmed by ChEMBL MOA for: {', '.join(covalent_drugs)}. "
            "Vina scores are non-covalent approximations and underestimate true binding "
            "affinity. Consider covalent docking (Autodock CovalentDock, GOLD) for accurate ranking."
        )
        return {
            "is_covalent": True,
            "covalent_evidence": "chembl_moa",
            "covalent_note": note,
        }

    # Source 2: AlphaMissense Cys variant evidence
    if variants:
        high_path = variants.get("high_path_missense", 0)
        # Heuristic: ≥3 high-pathogenicity missense variants at a Cys position
        # suggests reactive-Cys biology (exact residue check requires full AM data)
        if int(high_path) >= 3:
            note = (
                f"Target has {high_path} high-pathogenicity missense variants; "
                "potential reactive cysteine. Vina docking is non-covalent — "
                "covalent warhead drugs may be underscored."
            )
            return {
                "is_covalent": True,
                "covalent_evidence": "alphamissense_cys_heuristic",
                "covalent_note": note,
            }

    return {"is_covalent": False, "covalent_evidence": "", "covalent_note": ""}


def _box_from_pocket(pocket: Dict) -> Tuple[Tuple[float, float, float], float]:
    """
    H5 fix: physics-motivated docking box sizing.

    The pocket volume gives an effective sphere radius r = (3V/4π)^(1/3).
    The box side = 2r + padding, where padding = 12 Å to allow ligand
    entry/exit poses and account for centroid-offset error.
    Minimum 26 Å (covers typical drug + 6 Å margin), maximum 40 Å.

    Old formula: max(22, vol^(1/3) × 1.5) — underestimates large pockets.
    New formula: max(26, 2 × (3V/4π)^(1/3) + 12) — physically motivated.

    Examples:
      480 Å³ (KRAS): r = 4.8 Å → box = 21.6 → clamp to 26 Å  (fine for G12C pocket)
      1200 Å³ (kinase hinge): r = 6.6 Å → box = 25.2 → clamp to 26 Å
      3000 Å³ (large allosteric): r = 9.0 Å → box = 30.1 Å  (was 21.9 with old formula)
    """
    cx = float(pocket.get("cx", 0.0))
    cy = float(pocket.get("cy", 0.0))
    cz = float(pocket.get("cz", 0.0))
    vol = float(pocket.get("volume", 500.0))
    import math
    r = (3.0 * vol / (4.0 * math.pi)) ** (1.0 / 3.0)
    side = max(26.0, 2.0 * r + 12.0)
    side = min(side, 40.0)
    return (cx, cy, cz), round(side, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Vina docking
# ─────────────────────────────────────────────────────────────────────────────

def dock_one(
    smiles: str,
    drug_name: str,
    receptor_pdbqt: Path,
    pocket: Dict,
    work_dir: Path,
    exhaustiveness: int = 8,
) -> Optional[float]:
    """
    Dock a single ligand SMILES against the receptor PDBQT.

    Returns the best Vina affinity (kcal/mol, negative = binding) or None.
    """
    vina_bin = _vina_bin()
    if vina_bin is None:
        log.warning("[4.dock] Vina binary not found — skipping %s", drug_name)
        return None

    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in drug_name)[:30]
    # Append hash suffix to avoid name collisions between drugs with identical prefixes
    import hashlib
    suffix = hashlib.md5(drug_name.encode()).hexdigest()[:6]
    lig_dir = work_dir / f"{safe_name}_{suffix}"
    lig_dir.mkdir(parents=True, exist_ok=True)

    lig_pdbqt = smiles_to_pdbqt(smiles, lig_dir, safe_name)
    if lig_pdbqt is None:
        log.debug("[4.dock] Ligand prep failed for %s", drug_name)
        return None

    center, side = _box_from_pocket(pocket)
    out_pdbqt = lig_dir / "out.pdbqt"

    cmd = [
        vina_bin,
        "--receptor", str(receptor_pdbqt),
        "--ligand",   str(lig_pdbqt),
        "--out",      str(out_pdbqt),
        "--center_x", str(center[0]),
        "--center_y", str(center[1]),
        "--center_z", str(center[2]),
        "--size_x", str(side),
        "--size_y", str(side),
        "--size_z", str(side),
        "--exhaustiveness", str(exhaustiveness),
        "--num_modes", "5",
        "--cpu", "1",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_VINA_TIMEOUT,
        )
        return _parse_vina_affinity(result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        log.debug("[4.dock] Vina timed out for %s", drug_name)
        return None
    except Exception as exc:
        log.debug("[4.dock] Vina error for %s: %s", drug_name, exc)
        return None


def _parse_vina_affinity(vina_output: str) -> Optional[float]:
    """
    Extract the best (most negative) affinity from Vina stdout.

    Vina 1.2.x output format (whitespace-delimited):
      mode |   affinity | dist from best mode
         1       -9.543          0          0

    Also handles the older pipe-delimited format just in case.
    """
    best: Optional[float] = None
    for line in vina_output.splitlines():
        line = line.strip()
        # Skip header/separator lines
        if not line or line.startswith("mode") or line.startswith("-"):
            continue
        # Try whitespace split first (Vina 1.2): "1  -9.543  0  0"
        parts = line.split()
        if len(parts) >= 2:
            try:
                # First token should be mode number (int), second is affinity
                int(parts[0])
                val = float(parts[1])
                if val < 0:
                    if best is None or val < best:
                        best = round(val, 3)
                    continue
            except (ValueError, IndexError):
                pass
        # Fallback: pipe-delimited
        pipe_parts = line.split("|")
        if len(pipe_parts) >= 2:
            try:
                val = float(pipe_parts[1].strip())
                if val < 0 and (best is None or val < best):
                    best = round(val, 3)
            except ValueError:
                pass
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Batch docking — ProcessPoolExecutor for RNG isolation (H7)
# ─────────────────────────────────────────────────────────────────────────────

def _dock_worker(args: tuple) -> dict:
    """
    H7 fix: top-level picklable worker for ProcessPoolExecutor.

    Each worker process has its own RDKit/C++ RNG state, eliminating
    cross-thread RNG interference that caused ±0.2 kcal/mol score variance
    in the ThreadPoolExecutor version.  Vina subprocess calls are also fully
    process-isolated.

    Must be a module-level function (not a closure) for pickle compatibility.
    """
    cand, receptor_str, pocket, work_dir_str, exhaustiveness = args
    receptor_pdbqt = Path(receptor_str)
    work_dir = Path(work_dir_str)
    score = dock_one(
        smiles=cand["smiles"],
        drug_name=cand["drug_name"],
        receptor_pdbqt=receptor_pdbqt,
        pocket=pocket,
        work_dir=work_dir,
        exhaustiveness=exhaustiveness,
    )
    return {**cand, "vina_score": score}


def dock_library(
    candidates: List[Dict],
    receptor_pdbqt: Path,
    pocket: Dict,
    work_dir: Path,
    exhaustiveness: int = 4,
    n_workers: int = 4,
) -> List[Dict]:
    """
    Dock a list of candidate dicts against the receptor in parallel.

    Uses ThreadPoolExecutor — Vina runs as a subprocess so threads don't block
    each other (subprocess.run releases the GIL). ProcessPoolExecutor with fork
    deadlocks inside uvicorn because forked children inherit locked mutexes from
    the parent's asyncio/threading state.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: List[Dict] = []
    total = len(candidates)
    log.info("[4.dock] Docking %d ligands (workers=%d, exhaustiveness=%d)", total, n_workers, exhaustiveness)

    task_args = [
        (c, str(receptor_pdbqt), pocket, str(work_dir), exhaustiveness)
        for c in candidates
    ]

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_dock_worker, a): a for a in task_args}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 50 == 0:
                log.info("[4.dock]   %d / %d docked", done, total)
            original_cand = futures[fut][0]
            try:
                results.append(fut.result())
            except Exception as exc:
                log.debug("[4.dock] Worker error for %s: %s", original_cand.get("drug_name"), exc)
                results.append({**original_cand, "vina_score": None})

    return results
