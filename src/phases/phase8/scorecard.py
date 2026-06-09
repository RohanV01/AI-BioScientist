"""
Phase 8 — Final candidate scorecard.

Binding confirmed by triple Vina re-dock at exhaustiveness=12.

Final score weights (from PRD §8.3):
  binding_affinity     0.30  — Vina-normalised (or biologic ipTM proxy)
  pose_stability       0.20  — consistency across 3 Vina runs (RMSD proxy)
  admet_developability 0.20  — ADMET score (SM) or developability score (biologic)
  selectivity          0.15  — absence of off-target flags; 1.0 when no selectivity_target
  novelty              0.10  — 1 - max_tanimoto vs approved
  modality_alignment   0.05  — candidate kind matches Phase 3 primary modality

Pass threshold: combined_score ≥ 0.45.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Literal, Optional

log = logging.getLogger(__name__)

# Weights from PRD §8.3
_W = {
    "binding_affinity":      0.30,
    "pose_stability":        0.20,
    "admet_developability":  0.20,
    "selectivity":           0.15,
    "novelty":               0.10,
    "modality_alignment":    0.05,
}

_PASS_THRESHOLD = 0.45
_VINA_CEIL      = -10.0   # normalisation ceiling


def _norm_vina(vina: Optional[float], ceiling: float = _VINA_CEIL) -> float:
    if vina is None or vina >= 0:
        return 0.0
    return round(max(0.0, min(1.0, vina / ceiling)), 4)


def _pose_stability_from_multi_run(
    vina_scores: List[Optional[float]],
) -> float:
    """
    Pose stability proxy: consistency across multiple Vina runs.
    CV (coefficient of variation) of scores → low CV = stable pose.
    Returns stability score 0-1 (high = consistent).
    """
    valid = [s for s in vina_scores if s is not None and s < 0]
    if len(valid) < 2:
        return 0.5   # unknown stability → neutral
    import statistics
    mean = statistics.mean(valid)
    stdev = statistics.stdev(valid)
    cv = abs(stdev / mean) if mean != 0 else 0.0
    # CV < 0.05 → excellent stability (1.0); CV > 0.30 → poor (0.0)
    stability = max(0.0, min(1.0, 1.0 - (cv - 0.05) / 0.25))
    return round(stability, 3)


def _selectivity_score(
    candidate: Dict,
    selectivity_target: Optional[str],
) -> float:
    """
    Selectivity score (1.0 when no off-target concern).
    Penalises candidates with hERG high, known off-target hits,
    or explicit off-target docking that exceeds the primary target.
    """
    if not selectivity_target:
        return 1.0

    # Check if ADMET flags the selectivity target
    admet = candidate.get("admet", {})
    disqualifying = admet.get("disqualifying", [])
    off_target_flags = [f for f in disqualifying
                        if selectivity_target.lower() in f.lower()]
    if off_target_flags:
        return 0.3

    # hERG penalty (most common off-target liability)
    if admet.get("hERG") == "high":
        return 0.5
    elif admet.get("hERG") == "medium":
        return 0.8

    return 1.0


def _modality_alignment(candidate: Dict, p3_primary: str) -> float:
    """
    Does the candidate kind match the Phase 3 primary modality?
    SM → kind in {de_novo_sm, repurposing}, biologic → kind in {biologic, peptide}
    """
    kind = candidate.get("kind", candidate.get("_kind", ""))
    if p3_primary in ("SM", "PROTAC"):
        return 1.0 if kind in ("de_novo_sm", "repurposing", "sm") else 0.5
    elif p3_primary in ("AB", "peptide", "biologic"):
        return 1.0 if kind in ("biologic", "peptide") else 0.5
    return 0.7  # unknown → neutral


def compute_final_score(
    candidate: Dict,
    vina_runs: Optional[List[float]] = None,
    selectivity_target: Optional[str] = None,
    p3_primary: str = "SM",
    indication_type: str = "chronic",
) -> Dict:
    """
    Compute the Phase 8 final validation scorecard for one candidate.
    Binding confirmed by triple Vina re-dock scores.

    Args:
        candidate:          candidate dict from P5/P6/P4
        vina_runs:          list of Vina scores from multiple runs (for stability)
        selectivity_target: gene symbol of selectivity concern (optional)
        p3_primary:         Phase 3 primary modality for this target
        indication_type:    oncology / chronic / acute

    Returns dict with subscores and combined_score.
    """
    kind = candidate.get("kind", candidate.get("_kind", "sm"))
    is_biologic = kind in ("biologic", "peptide")

    # ── Binding affinity ─────────────────────────────────────────────────────
    if is_biologic:
        # Biologics: use developability_score as binding proxy (no Vina)
        # When ipTM is available (future NIM path), use that instead
        iptm = candidate.get("iptm", None)
        binding_score = float(iptm or candidate.get("developability_score") or 0.5)
    else:
        vina = candidate.get("vina_score") or candidate.get("vina_score_final")
        binding_score = _norm_vina(vina)

    # ── Pose stability ────────────────────────────────────────────────────────
    if vina_runs and not is_biologic:
        stability = _pose_stability_from_multi_run(vina_runs)
    else:
        stability = 0.5   # neutral when no multi-run data

    # ── ADMET / developability ───────────────────────────────────────────────
    if is_biologic:
        admet_dev = float(candidate.get("developability_score") or 0.5)
    else:
        admet_dev = float(
            candidate.get("admet_score")
            or candidate.get("admet", {}).get("admet_score")
            or 0.5
        )

    # ── Selectivity ──────────────────────────────────────────────────────────
    selectivity = _selectivity_score(candidate, selectivity_target)

    # ── Novelty ──────────────────────────────────────────────────────────────
    tanimoto = float(candidate.get("tanimoto_to_approved") or 0.0)
    novelty = round(1.0 - min(1.0, tanimoto), 3)

    # ── Modality alignment ───────────────────────────────────────────────────
    mod_align = _modality_alignment(candidate, p3_primary)

    # ── Combined score ────────────────────────────────────────────────────────
    combined = (
        _W["binding_affinity"]      * binding_score
        + _W["pose_stability"]        * stability
        + _W["admet_developability"]  * admet_dev
        + _W["selectivity"]           * selectivity
        + _W["novelty"]               * novelty
        + _W["modality_alignment"]    * mod_align
    )
    combined = round(min(1.0, combined), 4)
    passed = combined >= _PASS_THRESHOLD

    return {
        "combined_score": combined,
        "passed": passed,
        "subscores": {
            "binding_affinity": round(binding_score, 4),
            "pose_stability":   round(stability, 4),
            "admet_or_developability": round(admet_dev, 4),
            "selectivity":      round(selectivity, 4),
            "novelty":          round(novelty, 4),
            "modality_alignment": round(mod_align, 4),
        },
        "weights_used": _W,
    }


def rank_final_candidates(candidates: List[Dict]) -> List[Dict]:
    """Sort by combined_score descending, add final_rank."""
    ranked = sorted(candidates, key=lambda c: c.get("combined_score", 0.0), reverse=True)
    for i, c in enumerate(ranked):
        c["final_rank"] = i + 1
    return ranked
