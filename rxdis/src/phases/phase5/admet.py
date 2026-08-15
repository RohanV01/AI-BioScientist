"""
Phase 5 — Local ADMET prediction.

Uses RDKit descriptors + SMARTS-based alerts for rapid local ADMET scoring.
No external API required. Covers the most clinically significant endpoints:

  hERG    — cardiotoxicity (QT prolongation); SMARTS alert + logP/MW proxy
  AMES    — mutagenicity; structural alerts (Kazius 2005 + RDKit)
  BBB     — CNS penetration (for CNS indications)
  hepatox — structural hepatotoxicity alerts
  caco2   — oral absorption proxy (TPSA + MW)
  solubility — logS proxy (Delaney model)

Critical endpoint failures (>2) → disqualify compound.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Literal

log = logging.getLogger(__name__)

# SMARTS-based structural alerts
# hERG liability (basic nitrogen + aromatic + hydrophobic; simplified)
_HERG_SMARTS = [
    "[nH0;r5,r6]~[nH0;r5,r6]",           # bis-aromatic N
    "[n;r5,r6]~c~[n;r5,r6]",
    "c1ccc(NCc2ccccc2)cc1",               # diarylamine
    "[C;!$(C=O)](~[#7])~[C;!$(C=O)]~[#7]",  # double nitrogen aliphatic
]

# Ames mutagenicity alerts (Kazius/Baxter)
_AMES_SMARTS = [
    "[NX3;!$(NC=O)][N;!$(NC=O)]",        # hydrazine
    "O=[N+][O-]",                          # nitro
    "c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34",   # polycyclic aromatic
    "[CH2X4][F,Cl,Br,I]",                 # alpha halogens
    "S(=O)(=O)[OH]",                       # sulphonate
    "C(=O)[F,Cl,Br,I]",                   # acyl halide
    "[N;!$(NC=O)]C(=O)[N;!$(NC=O)]",      # semicarbazide
]

# Hepatotoxicity structural alerts
_HEPATOX_SMARTS = [
    "c1ccc(N)cc1",                         # aniline
    "[NX3H1,NX3H2]c1ccc(cc1)",           # aromatic amine
    "CC(=O)Oc1ccccc1",                     # aryl acetate
    "[CX4H1,CX4H2][F][F][F]",            # trifluoromethyl
]


def _compile_patterns():
    from rdkit import Chem
    out = {}
    for name, smarts_list in [
        ("herg", _HERG_SMARTS),
        ("ames", _AMES_SMARTS),
        ("hepatox", _HEPATOX_SMARTS),
    ]:
        patterns = []
        for s in smarts_list:
            try:
                p = Chem.MolFromSmarts(s)
                if p:
                    patterns.append(p)
            except Exception:
                pass
        out[name] = patterns
    return out


_COMPILED: Dict | None = None


def _get_patterns():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = _compile_patterns()
    return _COMPILED


# ─────────────────────────────────────────────────────────────────────────────
# Individual endpoint predictors
# ─────────────────────────────────────────────────────────────────────────────

def _predict_herg(mol, logp: float, mw: float) -> str:
    """
    hERG risk: low / medium / high.
    Structural alerts + logP>4 + MW 300-500 + basic nitrogen = risk.
    """
    patterns = _get_patterns()["herg"]
    alert_hits = sum(1 for p in patterns if mol.HasSubstructMatch(p))

    # Pharmacophoric rule: basic N + logP>2 + MW in drug range = hERG concern
    from rdkit.Chem import rdMolDescriptors
    n_basic = rdMolDescriptors.CalcNumHBA(mol)
    if alert_hits >= 2 or (logp > 4 and n_basic >= 2 and 300 < mw < 600):
        return "high"
    elif alert_hits == 1 or (logp > 3 and n_basic >= 1 and mw > 300):
        return "medium"
    return "low"


def _predict_ames(mol) -> str:
    """AMES mutagenicity: neg / pos."""
    patterns = _get_patterns()["ames"]
    for p in patterns:
        if mol.HasSubstructMatch(p):
            return "pos"
    return "neg"


def _predict_bbb(tpsa: float, mw: float, logp: float) -> str:
    """
    BBB penetration: pos / neg.
    Egan/Chou heuristic: TPSA<90, MW<400, logP<5 → CNS penetrant.
    """
    if tpsa < 90 and mw < 400 and 0 < logp < 5:
        return "pos"
    return "neg"


def _predict_hepatox(mol) -> str:
    """Hepatotoxicity structural alert: pos / neg."""
    patterns = _get_patterns()["hepatox"]
    for p in patterns:
        if mol.HasSubstructMatch(p):
            return "pos"
    return "neg"


def _predict_solubility(logp: float, mw: float) -> float:
    """
    Approximate logS (Delaney 2004 simplified):
      logS ≈ 0.16 - 0.63*logP - 0.0062*MW + 0.066*rotb - 0.74*aromatic_rings
    Returns logS value (> -4 = adequate solubility for oral drugs).
    """
    return round(0.16 - 0.63 * logp - 0.0062 * mw, 2)


def _predict_caco2(tpsa: float, mw: float) -> str:
    """
    Caco-2 permeability proxy (oral absorption).
    High: TPSA<60 and MW<450. Medium: TPSA<120. Low: otherwise.
    """
    if tpsa < 60 and mw < 450:
        return "high"
    elif tpsa < 120:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────────────────
# Main ADMET scorer
# ─────────────────────────────────────────────────────────────────────────────

def score_admet(
    smiles: str,
    indication_type: Literal["oncology", "chronic", "acute"] = "chronic",
    selectivity_target: str | None = None,
) -> Dict:
    """
    Score a single SMILES across ADMET endpoints.

    Returns dict with:
      hERG, AMES, BBB, hepatox, caco2, logS, critical_failures, passes,
      admet_score (0-1, higher=better), disqualifying, concerns
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
    except ImportError:
        return {"passes": True, "admet_score": 0.5, "critical_failures": 0,
                "error": "rdkit_not_available"}

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"passes": False, "admet_score": 0.0, "critical_failures": 1,
                "error": "invalid_smiles"}

    mw = round(Descriptors.ExactMolWt(mol), 1)
    logp = round(Descriptors.MolLogP(mol), 2)
    tpsa = round(Descriptors.TPSA(mol), 1)

    herg = _predict_herg(mol, logp, mw)
    ames = _predict_ames(mol)
    bbb = _predict_bbb(tpsa, mw, logp)
    hepatox = _predict_hepatox(mol)
    caco2 = _predict_caco2(tpsa, mw)
    logs = _predict_solubility(logp, mw)

    # Criticality depends on indication
    disqualifying = []
    concerns = []

    # hERG: always critical above medium for chronic/oncology
    if herg == "high":
        disqualifying.append(f"hERG_high_risk(logP={logp},MW={mw})")
    elif herg == "medium":
        concerns.append("hERG_medium_risk")

    # AMES: always critical
    if ames == "pos":
        disqualifying.append("AMES_mutagenic")

    # Hepatotoxicity: critical for chronic
    if hepatox == "pos":
        if indication_type == "chronic":
            disqualifying.append("hepatotoxicity_alert")
        else:
            concerns.append("hepatotoxicity_alert")

    # Solubility: critical if very insoluble
    if logs < -6:
        disqualifying.append(f"very_low_solubility(logS={logs})")
    elif logs < -4:
        concerns.append(f"low_solubility(logS={logs})")

    # BBB: relevant only for CNS indications (warn if non-CNS and BBB=pos for toxic)
    # caco2 low: concern for oral drugs
    if caco2 == "low":
        concerns.append("low_oral_absorption")

    n_critical = len(disqualifying)
    # Rule: >2 critical failures → disqualify (unless oncology with known exception)
    max_crit = 1 if indication_type == "chronic" else 2
    passes = n_critical <= max_crit

    # ADMET score: 1.0 = clean, penalties for each issue
    admet_score = 1.0
    admet_score -= 0.3 * min(2, n_critical)
    admet_score -= 0.1 * min(2, len(concerns))
    admet_score = round(max(0.0, admet_score), 3)

    return {
        "hERG": herg,
        "AMES": ames,
        "BBB": bbb,
        "hepatox": hepatox,
        "caco2": caco2,
        "logS": logs,
        "mw": mw,
        "logp": logp,
        "tpsa": tpsa,
        "disqualifying": disqualifying,
        "concerns": concerns,
        "critical_failures": n_critical,
        "admet_score": admet_score,
        "passes": passes,
    }


def batch_score_admet(
    smiles_list: List[str],
    indication_type: str = "chronic",
    selectivity_target: str | None = None,
) -> List[Dict]:
    """Score a list of SMILES. Returns same-length list of ADMET dicts."""
    results = []
    for smi in smiles_list:
        r = score_admet(smi, indication_type=indication_type,
                        selectivity_target=selectivity_target)
        r["smiles"] = smi
        results.append(r)
    n_pass = sum(1 for r in results if r["passes"])
    log.info("[5.admet] %d/%d compounds pass ADMET", n_pass, len(results))
    return results
