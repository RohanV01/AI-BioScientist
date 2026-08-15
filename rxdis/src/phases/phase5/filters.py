"""
Phase 5 — Medicinal-chemistry filters.

Applied in order:
  1. Sanitization / parse check
  2. Lipinski Ro5 (drug-likeness)
  3. Veber oral bioavailability (TPSA + rotatable bonds)
  4. PAINS (Pan-Assay Interference Compounds) — flag, not hard-drop
  5. SA score  < 6  (synthetic accessibility; Ertl & Schuffenhauer 2009)
  6. QED      > 0.3 (quantitative estimate of drug-likeness)
  7. Tanimoto novelty vs reference set < 0.7 (avoid known drugs unless analog seeding)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy RDKit imports
# ─────────────────────────────────────────────────────────────────────────────

def _rdkit():
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors, QED
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    return Chem, Descriptors, rdMolDescriptors, QED, FilterCatalog, FilterCatalogParams


def _sa_score(mol):
    """Synthetic accessibility score (1=easy, 10=hard). Uses RDKit's sascorer."""
    try:
        from rdkit.Chem import RDConfig
        import sys, os
        sa_path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if sa_path not in sys.path:
            sys.path.append(sa_path)
        import sascorer
        return sascorer.calculateScore(mol)
    except Exception:
        # Fallback: approximate via ring complexity
        try:
            from rdkit.Chem import rdMolDescriptors
            rings = rdMolDescriptors.CalcNumRings(mol)
            hbd = rdMolDescriptors.CalcNumHBD(mol)
            return min(9.0, 1.5 + rings * 0.4 + hbd * 0.2)
        except Exception:
            return 5.0


def _pains_catalog():
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    return FilterCatalog(params)


_pains_catalog_instance = None


def _get_pains():
    global _pains_catalog_instance
    if _pains_catalog_instance is None:
        _pains_catalog_instance = _pains_catalog()
    return _pains_catalog_instance


# ─────────────────────────────────────────────────────────────────────────────
# Individual filter functions
# ─────────────────────────────────────────────────────────────────────────────

def lipinski_ro5(mol) -> Tuple[bool, Dict]:
    """Lipinski Rule-of-5. Returns (pass, details)."""
    from rdkit.Chem import Descriptors, rdMolDescriptors
    mw = Descriptors.ExactMolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    violations = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
    return violations <= 1, {"mw": round(mw, 1), "logp": round(logp, 2),
                              "hbd": hbd, "hba": hba, "ro5_violations": violations}


def veber(mol) -> Tuple[bool, Dict]:
    """Veber oral bioavailability (TPSA ≤ 140, rotatable bonds ≤ 10)."""
    from rdkit.Chem import rdMolDescriptors, Descriptors
    tpsa = Descriptors.TPSA(mol)
    rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
    return (tpsa <= 140 and rotb <= 10), {"tpsa": round(tpsa, 1), "rotb": rotb}


def pains_check(mol) -> Tuple[bool, List[str]]:
    """PAINS check. Returns (is_clean, list_of_pains_names)."""
    catalog = _get_pains()
    matches = catalog.GetMatches(mol)
    names = [m.GetDescription() for m in matches]
    return len(names) == 0, names


def sa_filter(mol, threshold: float = 6.0) -> Tuple[bool, float]:
    """SA score filter. Returns (pass, sa_score)."""
    sa = _sa_score(mol)
    return sa < threshold, round(sa, 2)


def qed_filter(mol, threshold: float = 0.3) -> Tuple[bool, float]:
    """QED filter. Returns (pass, qed)."""
    from rdkit.Chem import QED as _qed
    q = _qed.qed(mol)
    return q >= threshold, round(q, 3)


def tanimoto_novelty(mol, reference_fps, threshold: float = 0.7) -> Tuple[bool, float]:
    """
    Returns (is_novel, max_tanimoto_to_reference).
    Novel = max Tanimoto to reference set < threshold.
    """
    if not reference_fps:
        return True, 0.0
    from rdkit.Chem import DataStructs
    from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
    gen = GetMorganGenerator(radius=2, fpSize=2048)
    fp = gen.GetFingerprint(mol)
    sims = DataStructs.BulkTanimotoSimilarity(fp, reference_fps)
    max_sim = max(sims) if sims else 0.0
    return max_sim < threshold, round(max_sim, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Batch filter pipeline
# ─────────────────────────────────────────────────────────────────────────────

def build_reference_fps(smiles_list: List[str]):
    """Build Morgan FP list from reference SMILES (ChEMBL approved drugs)."""
    from rdkit import Chem
    from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
    gen = GetMorganGenerator(radius=2, fpSize=2048)
    fps = []
    for smi in smiles_list:
        try:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                fps.append(gen.GetFingerprint(mol))
        except Exception:
            pass
    return fps


def apply_filters(
    smiles_list: List[str],
    reference_fps=None,
    novelty_threshold: float = 0.7,
    sa_threshold: float = 6.0,
    qed_threshold: float = 0.3,
    allow_pains: bool = False,
) -> List[Dict]:
    """
    Apply the full medichem filter pipeline to a list of SMILES.

    Returns list of dicts with keys:
      smiles, passes, fail_reason, mw, logp, hbd, hba, tpsa, rotb,
      sa_score, qed, tanimoto_to_approved, pains_flags, ro5_violations
    """
    from rdkit import Chem
    results = []

    for smi in smiles_list:
        record: Dict = {"smiles": smi, "passes": False, "fail_reason": ""}
        try:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                record["fail_reason"] = "invalid_smiles"
                results.append(record)
                continue

            # Ro5
            ro5_pass, ro5_info = lipinski_ro5(mol)
            record.update(ro5_info)

            # Veber
            veb_pass, veb_info = veber(mol)
            record.update(veb_info)

            # PAINS
            pains_clean, pains_names = pains_check(mol)
            record["pains_flags"] = pains_names

            # SA
            sa_pass, sa = sa_filter(mol, sa_threshold)
            record["sa_score"] = sa

            # QED
            qed_pass, q = qed_filter(mol, qed_threshold)
            record["qed"] = q

            # Novelty
            if reference_fps is not None:
                novel, max_sim = tanimoto_novelty(mol, reference_fps, novelty_threshold)
                record["tanimoto_to_approved"] = max_sim
            else:
                novel, record["tanimoto_to_approved"] = True, 0.0

            # Combine (PAINS is warn-only unless allow_pains=False and explicit drop)
            if not ro5_pass:
                record["fail_reason"] = f"ro5_violations={ro5_info['ro5_violations']}"
            elif not veb_pass:
                record["fail_reason"] = f"veber_fail(tpsa={record['tpsa']},rotb={record['rotb']})"
            elif not sa_pass:
                record["fail_reason"] = f"sa_score={sa:.1f}"
            elif not qed_pass:
                record["fail_reason"] = f"qed={q:.2f}"
            elif not novel:
                record["fail_reason"] = f"not_novel(tanimoto={record['tanimoto_to_approved']:.2f})"
            elif pains_names and not allow_pains:
                record["fail_reason"] = f"pains:{pains_names[0]}"
                record["passes"] = True   # PAINS: keep but flag
                record["pains_flagged"] = True
            else:
                record["passes"] = True

        except Exception as exc:
            record["fail_reason"] = f"error:{exc}"

        results.append(record)

    n_pass = sum(1 for r in results if r["passes"])
    log.info("[5.filter] %d/%d molecules pass filters", n_pass, len(results))
    return results
