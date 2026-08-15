"""
Phase 4 — Four-signal triangulation scoring for drug repurposing.

Signal weights when ALL signals available:
  docking  0.35   Structure-based pocket occupancy (Trott & Olson 2010)
  clinical 0.30   ChEMBL max_phase de-risking (Ashburn & Thor 2004)
  lincs    0.20   Transcriptomic reversal, phenotypic rescue (Lamb 2006, Science)
  kg       0.15   Curated drug-protein edges, PrimeKG

Fallback schemes:
  No LINCS:         docking(0.40) + clinical(0.35) + kg(0.25)
  No docking:       clinical(0.60) + kg(0.40)

B2 fix — empirical Vina calibration:
  Fixed ceiling of −12 kcal/mol was too aggressive; approved drugs score −5 to −10.
  New: `calibrate_vina_ceiling(scores)` computes the 95th-percentile score from the
  actual docked candidates and uses that as the ceiling (clamped to [−8.5, −12.0]).
  This spreads the normalization across the real distribution rather than wasting
  30% of the [0,1] scale on hypothetically excellent binders that never appear.

B3 fix — pass_mechanism and structural_evidence:
  `pass_mechanism`: "structural" | "transcriptomic" | "clinical" | "mixed"
  `structural_evidence`: True when vina_norm > 0.4 OR kg_score > 0.
  `lincs_dominant`: True when LINCS contributes more to score than docking+KG.
  These fields let the UI flag LINCS-primary hits (polypharmacology risk) without
  hard-filtering them — biologically they may be valid, but users should know.

  Additionally: `passed` now requires structural_evidence=True OR lincs_score > 0.5.
  Pure clinical-only candidates (approved drug, no structural or LINCS support)
  are kept in output but marked borderline, preventing aspirin-for-KRAS false passes.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

# 4-signal weights (LINCS available)
_W_DOCK  = 0.35
_W_CLIN  = 0.30
_W_LINCS = 0.20
_W_KG    = 0.15

# 3-signal fallback (no LINCS)
_W_DOCK_3  = 0.40
_W_CLIN_3  = 0.35
_W_KG_3    = 0.25

# No-docking fallback
_W_CLIN_FALLBACK = 0.60
_W_KG_FALLBACK   = 0.40

# Vina normalization bounds
_VINA_NO_BIND        = 0.0
_VINA_EXCELLENT_DEFAULT = -12.0   # conservative floor (calibrated per-run)
_VINA_CALIBRATED_MIN = -8.5       # minimum ceiling allowed after calibration
_VINA_CALIBRATED_MAX = -12.0      # maximum (most negative) ceiling allowed

# Score thresholds
_PASS_THRESHOLD = 0.30
_KEEP_THRESHOLD = 0.20

# B3: absolute Vina score threshold for structural evidence (kcal/mol).
# Must be more negative than this to count as a structural binder, regardless
# of ceiling calibration. −7.0 kcal/mol ≈ micromolar affinity for drug-sized ligands
# (Irwin et al. 2012, JCIM). Aspirin (−5.1) sits below this; sotorasib (−8.67) above.
_STRUCTURAL_VINA_ABS = -7.0


# ─────────────────────────────────────────────────────────────────────────────
# B2: Empirical Vina ceiling calibration
# ─────────────────────────────────────────────────────────────────────────────

def calibrate_vina_ceiling(vina_scores: List[Optional[float]]) -> float:
    """
    Compute the empirical Vina normalization ceiling from a list of scores.

    Uses the 95th percentile of non-None scores (i.e. the strongest 5% of binders).
    Clamps to [_VINA_CALIBRATED_MIN, _VINA_CALIBRATED_MAX] to prevent degenerate cases.

    Scientific basis: normalization to a fixed −12 kcal/mol ceiling wastes ~30%
    of the [0,1] scale because approved drugs rarely exceed −10 kcal/mol. Using the
    empirical 95th percentile ensures the top binders in the actual run score near 1.0,
    maximising discriminative power between strong and moderate binders.

    Falls back to _VINA_EXCELLENT_DEFAULT (−12) when fewer than 5 docked scores
    are available.
    """
    valid = sorted(
        [s for s in vina_scores if s is not None and s < 0],
        reverse=False,   # most negative first
    )
    if len(valid) < 5:
        return _VINA_EXCELLENT_DEFAULT

    pct95_idx = max(0, int(len(valid) * 0.05))   # 5th index from most-negative end
    ceiling = valid[pct95_idx]

    # Clamp: don't allow ceiling weaker than −8.5 or stronger than −12
    return round(max(_VINA_CALIBRATED_MAX, min(_VINA_CALIBRATED_MIN, ceiling)), 2)


def normalize_vina(
    vina_score: Optional[float],
    ceiling: float = _VINA_EXCELLENT_DEFAULT,
) -> float:
    """Map Vina kcal/mol → [0, 1] using the (possibly calibrated) ceiling."""
    if vina_score is None or vina_score >= _VINA_NO_BIND:
        return 0.0
    norm = vina_score / ceiling   # both negative → positive ratio
    return round(max(0.0, min(1.0, norm)), 4)


# ─────────────────────────────────────────────────────────────────────────────
# B3: pass_mechanism classification
# ─────────────────────────────────────────────────────────────────────────────

def _classify_mechanism(
    vina_norm: float,
    kg_score: float,
    lincs_score: float,
    clinical_score: float,
    weights: Dict[str, float],
    vina_score_raw: Optional[float] = None,
) -> Dict[str, object]:
    """
    Classify the primary evidence source for a candidate's repurposing score.

    Returns: structural_evidence (bool), lincs_dominant (bool), pass_mechanism (str).

    Scientific rationale:
      "Structural" evidence (docking + KG) confirms the drug can physically occupy
      the binding site and has a curated protein interaction record. LINCS evidence
      shows phenotypic rescue but doesn't confirm direct binding. Knowing which
      signal drives the score helps prioritise follow-up experiments:
        - structural-primary → docking validation / ITC binding assay
        - transcriptomic-primary → cell viability / DE assay to confirm reversal
        - clinical-primary → may be a class effect, not target-specific
    """
    # Use absolute Vina score for structural evidence — avoids ceiling-calibration artefacts
    vina_ok = (vina_score_raw is not None and vina_score_raw <= _STRUCTURAL_VINA_ABS)
    structural_evidence = vina_ok or kg_score > 0

    dock_contrib  = weights.get("docking", 0) * vina_norm
    kg_contrib    = weights.get("kg", 0) * kg_score
    lincs_contrib = weights.get("lincs", 0) * lincs_score
    clin_contrib  = weights.get("clinical", 0) * clinical_score

    # LINCS-dominant: strong LINCS signal AND no structural evidence.
    # Semantics: "this drug passes because it transcriptomically reverses the
    # disease, not because it physically binds the target pocket."
    lincs_dominant = lincs_score >= 0.5 and not structural_evidence

    # pass_mechanism: which evidence type contributes the most
    if lincs_dominant:
        pass_mechanism = "transcriptomic"
    elif dock_contrib + kg_contrib > clin_contrib:
        pass_mechanism = "structural"
    elif clin_contrib > dock_contrib + kg_contrib + lincs_contrib:
        pass_mechanism = "clinical"
    else:
        pass_mechanism = "mixed"

    return {
        "structural_evidence": structural_evidence,
        "lincs_dominant": lincs_dominant,
        "pass_mechanism": pass_mechanism,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main scoring function
# ─────────────────────────────────────────────────────────────────────────────

def compute_repurposing_score(
    vina_score: Optional[float],
    clinical_score: float,
    kg_score: float,
    lincs_score: float = 0.0,
    docking_available: bool = True,
    lincs_available: bool = False,
    vina_ceiling: float = _VINA_EXCELLENT_DEFAULT,
) -> Dict:
    """
    Compute the triangulated repurposing score for a single candidate.

    Returns a dict with: vina_norm, clinical_score, kg_score, lincs_score,
    repurposing_score, passed, borderline, weights_used, pass_mechanism,
    structural_evidence, lincs_dominant.
    """
    vn = normalize_vina(vina_score, ceiling=vina_ceiling)

    if docking_available and lincs_available:
        score = _W_DOCK * vn + _W_CLIN * clinical_score + _W_LINCS * lincs_score + _W_KG * kg_score
        weights = {"docking": _W_DOCK, "clinical": _W_CLIN, "lincs": _W_LINCS, "kg": _W_KG}
    elif docking_available:
        score = _W_DOCK_3 * vn + _W_CLIN_3 * clinical_score + _W_KG_3 * kg_score
        weights = {"docking": _W_DOCK_3, "clinical": _W_CLIN_3, "lincs": 0.0, "kg": _W_KG_3}
    else:
        score = _W_CLIN_FALLBACK * clinical_score + _W_KG_FALLBACK * kg_score
        weights = {"docking": 0.0, "clinical": _W_CLIN_FALLBACK, "lincs": 0.0, "kg": _W_KG_FALLBACK}

    score = round(min(1.0, score), 4)

    # B3: classify evidence type (pass raw vina_score for absolute threshold check)
    mech = _classify_mechanism(vn, kg_score, lincs_score, clinical_score, weights,
                               vina_score_raw=vina_score)

    # B3: passed = score >= threshold AND (structural evidence OR strong LINCS)
    # Prevents pure clinical-only (approved drug, no structural/LINCS support)
    # from passing — they score exactly at the 0.30 threshold in 4-signal mode.
    evidence_ok = mech["structural_evidence"] or lincs_score >= 0.5
    passed = score >= _PASS_THRESHOLD and evidence_ok

    return {
        "vina_norm": vn,
        "clinical_score": round(clinical_score, 4),
        "kg_score": round(kg_score, 4),
        "lincs_score": round(lincs_score, 4),
        "repurposing_score": score,
        "weights_used": weights,
        "passed": passed,
        "borderline": _KEEP_THRESHOLD <= score < _PASS_THRESHOLD or (score >= _PASS_THRESHOLD and not evidence_ok),
        **mech,
    }


def calibrate_and_rescore(
    candidates: List[Dict],
    docking_available: bool,
    lincs_available: bool,
) -> List[Dict]:
    """
    B2: Two-pass scoring.

    Pass 1: collect all Vina scores → calibrate ceiling.
    Pass 2: re-score all candidates with the calibrated ceiling.

    This ensures the normalization reflects the actual score distribution of
    this target's docked library rather than a fixed theoretical maximum.
    """
    vina_scores = [c.get("vina_score") for c in candidates]
    ceiling = calibrate_vina_ceiling(vina_scores)

    for c in candidates:
        scores = compute_repurposing_score(
            vina_score=c.get("vina_score"),
            clinical_score=float(c.get("clinical_score", 0.0)),
            kg_score=c.get("kg_score", 0.0),
            lincs_score=c.get("lincs_score", 0.0),
            docking_available=docking_available,
            lincs_available=lincs_available,
            vina_ceiling=ceiling,
        )
        c.update(scores)
        c["vina_ceiling_used"] = ceiling

    return candidates


def rank_candidates(candidates: List[Dict]) -> List[Dict]:
    """Sort by repurposing_score descending, add 'rank' (1-based)."""
    sorted_cands = sorted(
        candidates, key=lambda c: c.get("repurposing_score", 0.0), reverse=True
    )
    for i, c in enumerate(sorted_cands):
        c["rank"] = i + 1
    return sorted_cands


def filter_candidates(
    candidates: List[Dict],
    vina_threshold: float = -7.0,
    min_score: float = _KEEP_THRESHOLD,
) -> List[Dict]:
    """
    Remove candidates that clearly cannot bind.
    Borderline (passed=False, score in [min_score, PASS_THRESHOLD)) are kept
    but their `borderline=True` flag is already set by compute_repurposing_score.
    """
    out = []
    for c in candidates:
        vina = c.get("vina_score")
        if vina is not None and vina >= vina_threshold:
            continue
        if c.get("repurposing_score", 0.0) < min_score:
            continue
        out.append(c)
    return out
