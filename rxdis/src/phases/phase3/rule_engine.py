"""
Phase 3, Step 3.1: Deterministic rule-engine for modality scoring and routing.

Logic faithfully implements the PRD pseudocode.  No I/O — pure functions only.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_SECONDARY_THRESHOLD = 0.50


def score_modalities(target: Dict) -> Dict[str, float]:
    """
    Re-score modalities at Phase 3 resolution using Phase 2 evidence.

    Phase 2 tractability.py already produced per-modality scores; Phase 3
    refines them with repurposing context and safety adjustments.
    """
    modality = target.get("modality", {})
    safety = target.get("safety", {})
    max_drugg: float = target.get("max_druggability", 0.0)

    scores: Dict[str, float] = {}

    for key in ("SM", "AB", "PROTAC", "peptide", "oligo"):
        v = float(modality.get(key, 0.0))
        if v > 0:
            scores[key] = v

    if not scores:
        scores["AB"] = 0.75 if max_drugg < 0.3 else max(0.3, max_drugg * 0.8)

    # Safety: broad critical-tissue expression slightly penalises SM
    if safety.get("critical_tissue_flag") and "SM" in scores:
        scores["SM"] = round(scores["SM"] * 0.88, 3)

    return {k: round(v, 3) for k, v in scores.items() if v > 0}


def compute_repurposing_priority(target: Dict, evidence_trail: Dict) -> str:
    """
    Assign repurposing priority from OT tractability (proxy for clinical stage).

      ≥ 0.90  → HIGH          (approved drug exists)
      ≥ 0.70  → MEDIUM        (Phase 2/3 clinical candidate)
      ≥ 0.50  → LOW_CLINICAL  (Phase 1 candidate)
      < 0.50  → LOW
    """
    ot_tractability = float(evidence_trail.get("tractability", 0.0))
    clinical_stage = str(evidence_trail.get("clinical_stage", "")).lower()

    if clinical_stage == "approved" or ot_tractability >= 0.90:
        return "HIGH"
    if clinical_stage in {"clinical_ph2", "clinical_ph3"} or ot_tractability >= 0.70:
        return "MEDIUM"
    if clinical_stage == "clinical_ph1" or ot_tractability >= 0.50:
        return "LOW_CLINICAL"
    return "LOW"


def apply_intent_routing(
    *,
    primary: str,
    secondary: Optional[str],
    repurposing_priority: str,
    intent_mode: str,
    budget_allows_secondary: bool = True,
) -> List[str]:
    """
    Translate modality + intent_mode into downstream phase branches.

    Branch rules (PRD §3.2):
      repurpose  → P4 only; no de novo branches
      de_novo    → skip P4; P5 if SM/PROTAC primary; P6 if AB/peptide primary
      explore    → always P4; plus primary de novo branch; secondary if budget
    """
    branches: List[str] = []
    _sm_like  = {"SM", "PROTAC"}
    _bio_like = {"AB", "peptide"}

    if intent_mode in {"explore", "repurpose"}:
        branches.append("P4_repurpose")

    if intent_mode in {"explore", "de_novo"}:
        if primary in _sm_like:
            branches.append("P5_small_molecule")
        elif primary in _bio_like:
            branches.append("P6_biologic")

        if secondary and budget_allows_secondary:
            if secondary in _sm_like and "P5_small_molecule" not in branches:
                branches.append("P5_small_molecule")
            elif secondary in _bio_like and "P6_biologic" not in branches:
                branches.append("P6_biologic")

    return branches


def route_target(
    *,
    target: Dict,
    intent_mode: str,
    modality_preference: str = "any",
    seed_smiles_present: bool = False,
    novelty_mode: bool = False,
    provider=None,
    db=None,
    run_id: str = "",
) -> Dict:
    """
    Orchestrate Phase 3 routing for a single validated target.

    Wires together score_modalities → compute_repurposing_priority →
    apply_intent_routing into one result dict. The runner imports this.
    """
    modality_data = target.get("modality", {})
    safety = target.get("safety", {})
    max_drugg = float(target.get("max_druggability", 0.0))
    evidence_trail = target.get("evidence_trail", {})

    # score_modalities expects {modality: {SM:…}, safety: {…}, max_druggability:…}
    modality_scores_raw = modality_data.get("scores", modality_data)
    scores = score_modalities({
        "modality": modality_scores_raw,
        "safety": safety,
        "max_druggability": max_drugg,
    })

    # Fall back to Phase 2 primary/secondary if scorer produces nothing
    if not scores:
        primary_raw = modality_data.get("primary") or "SM"
        scores = {primary_raw: 0.6}

    # Apply hard modality preference override
    if modality_preference != "any":
        pref_map = {"small_molecule": "SM", "biologic": "AB", "peptide": "peptide"}
        pref_key = pref_map.get(modality_preference)
        if pref_key and pref_key not in scores:
            scores[pref_key] = 0.50

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_scores[0][0]
    secondary: Optional[str] = None
    if len(sorted_scores) > 1 and sorted_scores[1][1] >= _SECONDARY_THRESHOLD:
        secondary = sorted_scores[1][0]

    repurposing_priority = compute_repurposing_priority(target, evidence_trail)

    branches = apply_intent_routing(
        primary=primary,
        secondary=secondary,
        repurposing_priority=repurposing_priority,
        intent_mode=intent_mode,
        budget_allows_secondary=not novelty_mode,
    )

    return {
        "symbol": target.get("symbol", ""),
        "primary": primary,
        "secondary": secondary,
        "branches": branches,
        "repurposing_priority": repurposing_priority,
        "modality_scores": scores,
    }
