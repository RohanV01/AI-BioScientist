"""
Phase 2.8 — Tractability assessment & modality hint.

A rule engine over the biophysical profile assembled in 2.1–2.7 produces a
per-modality eligibility score; an LLM gate (2.8_tractability_edge) refines
genuinely ambiguous cases. Phase 3 consumes these scores for authoritative
branch routing — this step is the biophysics-grounded prior.

`selectivity_target` (config) is always added to the off-target hazard list
(PRD success criterion 4).
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from src.llm.provider import LLMProvider
from src.db.run_state import log_decision
from .schemas import TractabilityEdge

log = logging.getLogger(__name__)

_EDGE_DELTA = 0.1
_BORDERLINE_DRUG = (0.45, 0.55)


def assess_modality(
    *,
    symbol: str,
    localization: Dict,
    pockets: Dict,
    chembl: Dict,
    variants: Dict,
    structure: Dict,
    selectivity_target: Optional[str],
    provider: Optional[LLMProvider] = None,
    db=None,
    run_id: str = "",
) -> Dict:
    druggability = pockets.get("max_druggability", 0.0)
    chembl_evidence = min(1.0, chembl.get("n_potent", 0) / 50.0)
    intracellular = localization.get("is_intracellular", True)
    has_ecd = localization.get("has_ecd", False)
    is_secreted = localization.get("is_secreted", False)
    is_membrane = localization.get("is_membrane", False)
    # A high AlphaMissense pathogenic burden reflects evolutionary constraint, NOT
    # necessarily an activating gain-of-function. We treat it only as a weak flag
    # that routes the modality choice to the LLM gate (which weighs degradation vs
    # inhibition) — it does NOT itself bump any modality score.
    constraint_flag = variants.get("high_path_missense", 0) >= 10

    scores: Dict[str, float] = {"SM": 0.0, "PROTAC": 0.0, "peptide": 0.0,
                                "AB": 0.0, "oligo": 0.0}

    # Small molecule: needs a druggable pocket + chemical matter.
    if druggability > 0.5 and chembl.get("has_chemical_matter"):
        scores["SM"] = round(0.8 * druggability + 0.2 * chembl_evidence, 3)
    elif druggability > 0.5:
        scores["SM"] = round(0.7 * druggability, 3)

    # PROTAC: intracellular, even a weak binder / pocket is enough.
    if intracellular and (druggability > 0.2 or chembl.get("n_bioactive", 0) > 0):
        scores["PROTAC"] = 0.7

    # Antibody: extracellular target or membrane protein with an ECD.
    if is_secreted or (is_membrane and has_ecd):
        scores["AB"] = 0.85

    # Peptide: PPI / small extracellular interface.
    if is_secreted or (is_membrane and has_ecd):
        scores["peptide"] = 0.75
    elif intracellular and structure.get("n_residues", 9999) < 150:
        scores["peptide"] = 0.55

    # Oligo: intracellular & undruggable (knock down rather than inhibit).
    if intracellular and druggability < 0.5:
        scores["oligo"] = 0.6

    primary, secondary = _rank(scores)
    edge = _is_edge(scores, druggability, constraint_flag)

    # LLM grey-zone refinement.
    if edge and provider is not None:
        refined = _llm_edge_gate(symbol, scores, localization, pockets, chembl,
                                 constraint_flag, provider, db, run_id)
        if refined:
            scores = {k: refined[k] for k in scores}
            primary = refined["primary_recommendation"]
            _, secondary = _rank(scores)

    hazards = _off_target_hazards(symbol, selectivity_target)

    return {
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "primary": primary,
        "secondary": secondary,
        "edge_case": edge,
        "off_target_hazards": hazards,
    }


def _rank(scores: Dict[str, float]):
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0] if ranked and ranked[0][1] > 0 else "none"
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0.5 else None
    return primary, secondary


def _is_edge(scores: Dict[str, float], druggability: float, constraint_flag: bool) -> bool:
    ordered = sorted(scores.values(), reverse=True)
    top_two_close = len(ordered) >= 2 and (ordered[0] - ordered[1]) < _EDGE_DELTA and ordered[0] > 0
    borderline = _BORDERLINE_DRUG[0] <= druggability <= _BORDERLINE_DRUG[1]
    return bool(top_two_close or borderline or constraint_flag)


def _llm_edge_gate(symbol, scores, localization, pockets, chembl, constraint_flag,
                   provider, db, run_id) -> Optional[Dict]:
    prompt = (
        f"Target {symbol}. Decide drug-modality eligibility (0-1 each) and a primary "
        f"recommendation. This is a borderline case.\n\n"
        f"Localization: {localization.get('compartment')} "
        f"(membrane={localization.get('is_membrane')}, secreted={localization.get('is_secreted')}, "
        f"ECD={localization.get('has_ecd')})\n"
        f"Max pocket druggability: {pockets.get('max_druggability')} "
        f"(detection={pockets.get('detection')})\n"
        f"ChEMBL chemical matter: {chembl.get('n_potent')} potent compounds, "
        f"max clinical phase {chembl.get('max_phase')}\n"
        f"High evolutionary-constraint flag (many predicted-pathogenic missense): {constraint_flag}\n"
        f"Rule-engine scores so far: {scores}\n\n"
        "Modalities: SM (small molecule), PROTAC (degrader), peptide, AB (antibody), "
        "oligo (antisense/siRNA). Intracellular undruggable + GoF often favours PROTAC; "
        "extracellular favours AB/peptide. Return scores for all five, a primary "
        "recommendation, and one sentence of reasoning."
    )
    try:
        result = provider.complete(prompt, schema=TractabilityEdge, temperature=0.1)
    except Exception as exc:
        log.warning("[2.8] %s edge gate failed: %s", symbol, exc)
        return None
    if not result.parsed:
        return None
    if db:
        log_decision(db, run_id=run_id, phase=2, gate="2.8_tractability_edge",
                     provider=provider.name, model=provider.model,
                     prompt=prompt, raw_response=result.text, decision_json=result.parsed)
    return result.parsed


def _off_target_hazards(symbol: str, selectivity_target: Optional[str]) -> List[str]:
    hazards: List[str] = []
    if selectivity_target and selectivity_target != symbol:
        hazards.append(f"anti-target:{selectivity_target}")
    return hazards
