"""
Phase 5 — Molecule generation.

Primary path (when REINVENT4 is installed):
  Mol2Mol mode conditioned on ChEMBL seed SMILES → novel analogs.
  Installed via: pip install git+https://github.com/MolecularAI/REINVENT4.git

Fallback path (always available):
  BRICS fragmentation of ChEMBL binders → recombination → de-duplication.
  Produces 200–2000 novel SMILES per target using only RDKit.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

_REINVENT_BIN = shutil.which("reinvent") or shutil.which("reinvent4")

# Minimal diverse drug-like seed set for BRICS fallback when no target-specific seeds
# are available. These molecules contain BRICS-breakable bonds (amides, ethers, sulfonamides)
# so the fragment-recombination engine can produce novel analogs.
_SCAFFOLD_FALLBACK_SMILES = [
    "CC(=O)Nc1ccc(O)cc1",                   # paracetamol (aniline-amide)
    "Cc1ccc(S(N)(=O)=O)cc1",                # toluenesulfonamide
    "c1ccc(CN2CCNCC2)cc1",                  # benzyl-piperazine
    "O=C(Nc1ccccn1)c1ccccc1",              # picolinamide
    "CC1CCN(Cc2ccccc2)CC1",                 # N-benzyl methylpiperidine
    "O=C(O)c1ccc(Nc2ncccn2)cc1",           # 4-aminopyrimidine-benzoic acid
    "CN1CCC(c2ccccc2)CC1",                  # 4-phenyl-N-methyl piperidine
    "O=C(NCc1ccccc1)c1ccncc1",             # isonicotinoyl-benzylamine
    "CC(C)Cc1ccc(C(C)C(=O)O)cc1",          # ibuprofen
    "O=C(Nc1ccc(F)cc1)c1ccc(Cl)cc1",       # chloro-fluoro benzamide
    "Cc1nc2ccccc2c(=O)[nH]1",              # 2-methylbenzimidazolone
    "O=c1[nH]cnc2cncnc12",                 # hypoxanthine
]


# ─────────────────────────────────────────────────────────────────────────────
# REINVENT4 path
# ─────────────────────────────────────────────────────────────────────────────

def _write_reinvent_toml(
    work_dir: Path,
    seed_smiles: List[str],
    n_steps: int,
    batch_size: int,
) -> Path:
    """Write a minimal Mol2Mol REINVENT4 TOML config."""
    seeds_file = work_dir / "seeds.smi"
    seeds_file.write_text("\n".join(seed_smiles))

    toml_content = f"""
[parameters]
use_cuda = false
num_steps = {n_steps}
batch_size = {batch_size}

[parameters.diversity_filter]
type = "IdenticalTopologicalScaffold"
bucket_size = 25
minscore = 0.2
minsimilarity = 0.4

[parameters.inception]
memory_size = 100
sample_size = 10

[stage]
type = "Mol2Mol"

[stage.input]
smiles_file = "{seeds_file}"
sample_strategy = "multinomial"
temperature = 1.2

[stage.scoring]
type = "CustomSum"

[[stage.scoring.component]]
[stage.scoring.component.QED]
[stage.scoring.component.QED.endpoint]
name = "QED"
weight = 1.0

[[stage.scoring.component]]
[stage.scoring.component.SASCore]
[stage.scoring.component.SASCore.endpoint]
name = "SA_score"
weight = 0.5
transform.type = "reverse_sigmoid"
transform.high = 6.0
transform.low = 2.0
transform.k = 0.5
"""
    toml_path = work_dir / "reinvent_config.toml"
    toml_path.write_text(toml_content)
    return toml_path


def generate_with_reinvent4(
    seed_smiles: List[str],
    n_generate: int = 500,
    work_dir: Optional[Path] = None,
) -> List[str]:
    """
    Run REINVENT4 Mol2Mol to generate analogs from seed SMILES.
    Returns list of generated SMILES strings (empty if REINVENT4 unavailable).
    """
    if not _REINVENT_BIN:
        log.info("[5.gen] REINVENT4 not on PATH — using BRICS fallback")
        return []
    if not seed_smiles:
        return []

    tmp = work_dir or Path(tempfile.mkdtemp(prefix="rxdis_r4_"))
    try:
        n_steps = max(10, n_generate // len(seed_smiles))
        batch_size = min(64, n_generate)
        toml_path = _write_reinvent_toml(tmp, seed_smiles[:20], n_steps, batch_size)
        output_csv = tmp / "reinvent_output.csv"

        cmd = [_REINVENT_BIN, "--config", str(toml_path), "--output", str(output_csv)]
        log.info("[5.gen] Running REINVENT4: %d seeds × %d steps", len(seed_smiles), n_steps)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            log.warning("[5.gen] REINVENT4 exited %d: %s", result.returncode,
                        result.stderr[:300])
            return []

        generated = []
        if output_csv.exists():
            import csv
            with open(output_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    smi = row.get("SMILES") or row.get("smiles") or ""
                    if smi:
                        generated.append(smi.strip())
        log.info("[5.gen] REINVENT4 produced %d SMILES", len(generated))
        return generated

    except subprocess.TimeoutExpired:
        log.warning("[5.gen] REINVENT4 timed out")
        return []
    except Exception as exc:
        log.warning("[5.gen] REINVENT4 error: %s", exc)
        return []
    finally:
        if work_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# BRICS fallback
# ─────────────────────────────────────────────────────────────────────────────

def generate_with_brics(
    seed_smiles: List[str],
    n_generate: int = 1000,
) -> List[str]:
    """
    BRICS fragmentation + recombination fallback.
    Fragments seed molecules (known binders) and recombines fragments
    to produce novel drug-like candidates.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.BRICS import BRICSDecompose, BRICSBuild
        from rdkit.Chem import rdMolDescriptors
    except ImportError:
        log.error("[5.gen] RDKit not available")
        return []

    mols = []
    for smi in seed_smiles:
        try:
            m = Chem.MolFromSmiles(smi)
            if m:
                mols.append(m)
        except Exception:
            pass

    if not mols:
        log.warning("[5.gen] No valid seed molecules for BRICS")
        return []

    # Collect fragments from all seeds
    all_fragments: set[str] = set()
    for mol in mols:
        try:
            frags = BRICSDecompose(mol)
            all_fragments.update(frags)
        except Exception:
            pass

    if not all_fragments:
        log.warning("[5.gen] BRICS produced no fragments")
        return []

    # Convert fragments to mols
    frag_mols = []
    for fsmi in all_fragments:
        try:
            fm = Chem.MolFromSmiles(fsmi)
            if fm:
                frag_mols.append(fm)
        except Exception:
            pass

    log.info("[5.gen] BRICS: %d fragments from %d seeds", len(frag_mols), len(mols))

    # Recombine: BRICSBuild generates molecules from fragment set
    generated_smiles = set()
    try:
        # BRICSBuild is a generator — cap at n_generate
        builder = BRICSBuild(frag_mols)
        for i, new_mol in enumerate(builder):
            if i >= n_generate * 3:
                break
            try:
                smi = Chem.MolToSmiles(new_mol)
                if smi:
                    generated_smiles.add(smi)
                if len(generated_smiles) >= n_generate:
                    break
            except Exception:
                pass
    except Exception as exc:
        log.warning("[5.gen] BRICSBuild error: %s", exc)

    result = list(generated_smiles)
    log.info("[5.gen] BRICS generated %d unique SMILES", len(result))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_molecules(
    seed_smiles: List[str],
    n_generate: int = 1000,
    work_dir: Optional[Path] = None,
) -> List[str]:
    """
    Generate novel small molecules from seed SMILES.
    Tries REINVENT4 first; falls back to BRICS if unavailable or empty.
    """
    if not seed_smiles:
        log.warning("[5.gen] No target-specific seed SMILES — using built-in scaffold library as fallback")
        seed_smiles = _SCAFFOLD_FALLBACK_SMILES[:]

    # Try REINVENT4 primary path
    generated = generate_with_reinvent4(seed_smiles, n_generate=n_generate, work_dir=work_dir)

    # BRICS fallback
    if not generated:
        generated = generate_with_brics(seed_smiles, n_generate=n_generate)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for smi in generated:
        if smi not in seen:
            seen.add(smi)
            unique.append(smi)

    log.info("[5.gen] Final: %d unique generated SMILES", len(unique))
    return unique
