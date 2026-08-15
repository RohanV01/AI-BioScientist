"""
Phase 7 — Pareto front computation and hypervolume indicator.

Uses pure Python + numpy (no BoTorch/DEAP required).
The hypervolume improvement is used as the convergence criterion for the
active-learning loop in runner.py.

Scientific basis:
  Zitzler & Thiele 1999 — hypervolume indicator for multi-objective optimisation.
  Emmerich & Deutz 2018 — hypervolume improvement as acquisition function.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Pareto dominance
# ─────────────────────────────────────────────────────────────────────────────

def _dominates(a: List[float], b: List[float]) -> bool:
    """
    Return True if solution a Pareto-dominates b (maximisation).
    a dominates b iff a is at least as good on ALL objectives
    and strictly better on at least one.
    """
    at_least_as_good = all(ai >= bi for ai, bi in zip(a, b))
    strictly_better  = any(ai > bi  for ai, bi in zip(a, b))
    return at_least_as_good and strictly_better


def compute_pareto_front(
    candidates: List[Dict],
    objective_keys: List[str],
) -> Tuple[List[Dict], List[Dict]]:
    """
    Partition candidates into Pareto front (non-dominated) and dominated sets.

    Args:
        candidates:     list of candidate dicts
        objective_keys: keys to use as objectives (all maximised)

    Returns:
        (front, dominated)
    """
    n = len(candidates)
    dominated_flags = [False] * n

    obj_vecs = []
    for c in candidates:
        vec = [float(c.get(k) or 0.0) for k in objective_keys]
        obj_vecs.append(vec)

    for i in range(n):
        if dominated_flags[i]:
            continue
        for j in range(n):
            if i == j or dominated_flags[j]:
                continue
            if _dominates(obj_vecs[j], obj_vecs[i]):
                dominated_flags[i] = True
                break

    front     = [c for c, flag in zip(candidates, dominated_flags) if not flag]
    dominated = [c for c, flag in zip(candidates, dominated_flags) if flag]
    return front, dominated


# ─────────────────────────────────────────────────────────────────────────────
# Hypervolume (WFG algorithm — exact, works for low-dimensional objectives)
# ─────────────────────────="────────────────────────────────────────────────────

def _hv_2d(points: List[Tuple[float, float]], ref: Tuple[float, float]) -> float:
    """2D hypervolume via sweep line."""
    pts = sorted([(p[0], p[1]) for p in points if p[0] > ref[0] and p[1] > ref[1]],
                 key=lambda p: p[0], reverse=True)
    hv = 0.0
    prev_y = ref[1]
    for x, y in pts:
        if y > prev_y:
            hv += (x - ref[0]) * (y - prev_y)
            prev_y = y
    return hv


def compute_hypervolume(
    front: List[Dict],
    objective_keys: List[str],
    ref_point: Optional[List[float]] = None,
) -> float:
    """
    Compute the hypervolume indicator for a Pareto front.

    Uses 2D implementation (sufficient for 2 objectives).
    For >2 objectives, falls back to dominated hypervolume approximation.

    ref_point defaults to [0, 0, ...] (all zeros = nadir for [0,1]-normalised objectives).
    """
    if not front or len(objective_keys) < 2:
        return 0.0

    n_obj = len(objective_keys)
    if ref_point is None:
        ref_point = [0.0] * n_obj

    points = []
    for c in front:
        vec = tuple(float(c.get(k) or 0.0) for k in objective_keys)
        points.append(vec)

    if n_obj == 2:
        return _hv_2d(
            [(p[0], p[1]) for p in points],
            (ref_point[0], ref_point[1]),
        )

    # For >2 objectives: approximate as pairwise 2D HV (conservative)
    hv = 0.0
    for i in range(n_obj - 1):
        for j in range(i + 1, n_obj):
            hv += _hv_2d(
                [(p[i], p[j]) for p in points],
                (ref_point[i], ref_point[j]),
            )
    return hv / max(1, (n_obj * (n_obj - 1)) // 2)


# ─────────────────────────────────────────────────────────────────────────────
# Desirability (scalar aggregation of a Pareto front member)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_WEIGHTS = {
    "potency":       0.30,
    "admet_score":   0.25,
    "novelty":       0.15,
    "developability": 0.15,
    "selectivity":   0.15,
}


def compute_desirability(
    candidate: Dict,
    objective_keys: List[str],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Weighted sum desirability for scalar ranking within the Pareto front."""
    w = weights or _DEFAULT_WEIGHTS
    total_w = sum(w.get(k, 1.0 / len(objective_keys)) for k in objective_keys)
    score = 0.0
    for k in objective_keys:
        val = float(candidate.get(k) or 0.0)
        score += (w.get(k, 1.0 / len(objective_keys)) / total_w) * val
    return round(min(1.0, score), 4)
