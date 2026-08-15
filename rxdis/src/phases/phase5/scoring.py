"""
Phase 5 — De Novo SM combined pre-Phase-8 score.

combined_pre8 = 0.40*docking + 0.25*admet + 0.20*qed + 0.15*novelty

Where:
  docking  — Vina-normalised (ceiling calibrated from run; fallback -10 kcal/mol)
  admet    — ADMET score from admet.py (0-1)
  qed      — QED from RDKit (0-1)
  novelty  — 1 - max_tanimoto_to_approved (higher = more novel)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

_W_DOCK   = 0.40
_W_ADMET  = 0.25
_W_QED    = 0.20
_W_NOVEL  = 0.15

_VINA_FLOOR   = 0.0       # no binding
_VINA_CEIL_DEFAULT = -10.0  # kcal/mol; calibrated per-run if enough scores


def _norm_vina(vina: Optional[float], ceiling: float) -> float:
    if vina is None or vina >= 0:
        return 0.0
    return round(max(0.0, min(1.0, vina / ceiling)), 4)


def calibrate_ceiling(vina_scores: List[Optional[float]]) -> float:
    valid = sorted([s for s in vina_scores if s is not None and s < 0])
    if len(valid) < 3:
        return _VINA_CEIL_DEFAULT
    idx = max(0, int(len(valid) * 0.05))
    return round(max(-12.0, min(-8.0, valid[idx])), 2)


def score_candidate(
    vina_score: Optional[float],
    admet_score: float,
    qed: float,
    tanimoto_to_approved: float,
    vina_ceiling: float = _VINA_CEIL_DEFAULT,
) -> Dict:
    vina_norm = _norm_vina(vina_score, vina_ceiling)
    novelty = round(1.0 - min(1.0, tanimoto_to_approved), 4)

    combined = (
        _W_DOCK  * vina_norm
        + _W_ADMET * admet_score
        + _W_QED   * qed
        + _W_NOVEL * novelty
    )
    combined = round(min(1.0, combined), 4)

    passed = (
        combined >= 0.35
        and admet_score >= 0.5
        and (vina_score is None or vina_score <= -7.0)
    )

    return {
        "vina_norm": vina_norm,
        "admet_score": admet_score,
        "qed": qed,
        "novelty": novelty,
        "combined_pre8": combined,
        "passed": passed,
        "weights_used": {
            "docking": _W_DOCK, "admet": _W_ADMET,
            "qed": _W_QED, "novelty": _W_NOVEL,
        },
    }


def rank_candidates(candidates: List[Dict]) -> List[Dict]:
    ranked = sorted(candidates, key=lambda c: c.get("combined_pre8", 0.0), reverse=True)
    for i, c in enumerate(ranked):
        c["rank"] = i + 1
    return ranked
