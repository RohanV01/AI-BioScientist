"""
Phase 3 rule engine — modality routing per validated target.

Consumes Phase 2 modality scores (already biophysics-grounded with an LLM edge
gate) and applies:
  3.2 intent_mode routing      → which de-novo / repurposing branches are eligible
  3.3 config overrides         → modality_preference bias, seed_smiles → SM opt-only
  3.4 repurposing priority     → from ChEMBL max clinical phase (proxy for the PRD's
                                  Phase-1 `clinical_stage`, which this build does not
                                  yet emit per target)

The grey-zone LLM gate (3_modality_greyzone) is invoked only when the top two
modality scores are within 0.1, druggability is borderline, or a gain-of-function
signal conflicts with the rule-engine pick.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from src.llm.provider import LLMProvider
from src.db.run_state import log_decision
from .schemas import ModalityGreyzone

log = logging.getLogger(__name__)

_GREYZONE_DELTA = 0.1
_SECONDARY_CUTOFF = 0.5

# Modality → de-novo design phase.
_DENOVO_PHASE = {
    "SM": "P5_small_molecule",
    "PROTAC": "P5_small_molecule",
    "peptide": "P6_biologic",
    "AB": "P6_biologic",
    "oligo": "P6_biologic",
}


def route_target(
    *,
    target: Dict,
    intent_mode: str,
    modality_preference: str,
    seed_smiles_present: bool,
    novelty_mode: bool,
    provider: Optional[LLMProvider] = None,
    db=None,
    run_id: str = "",
) -> Dict:
    """Return the routing record for one validated target."""
    symbol = target["symbol"]
    scores: Dict[str, float] = dict(target.get("modality", {}).get("scores", {}))
    if not scores:
        scores = {"SM": 0.0, "PROTAC": 0.0, "peptide": 0.0, "AB": 0.0, "oligo": 0.0}

    is_seed = target.get("seeded", False)
    chembl = target.get("chembl", {})
    gof_hint = target.get("variants", {}).get("high_path_missense", 0) >= 10

    # ── 3.3 modality_preference bias ──────────────────────────────────────────
    pref_map = {"small_molecule": "SM", "biologic": "AB", "peptide": "peptide"}
    if modality_preference in pref_map:
        scores[pref_map[modality_preference]] = min(1.0, scores.get(pref_map[modality_preference], 0.0) + 0.15)

    primary, secondary = _rank(scores)

    # ── grey-zone resolution ──────────────────────────────────────────────────
    greyzone = _is_greyzone(scores, target, gof_hint)
    concerns: List[str] = []
    if greyzone and provider is not None:
        decision = _llm_greyzone(symbol, scores, target, gof_hint, provider, db, run_id)
        if decision:
            if decision["decision"] in scores:
                primary = decision["decision"]
                _, secondary = _rank({k: v for k, v in scores.items() if k != primary})
            concerns = decision.get("concerns", [])

    # ── 3.4 repurposing priority (ChEMBL max_phase proxy) ─────────────────────
    repurposing_priority = _repurposing_priority(chembl.get("max_phase", 0))

    # ── 3.2 intent_mode → branches ────────────────────────────────────────────
    branches = _branches(intent_mode, primary, secondary, repurposing_priority,
                         novelty_mode)

    # ── 3.3 seed_smiles → force SM optimization-only ──────────────────────────
    seed_smiles_opt = False
    if seed_smiles_present and is_seed:
        primary = "SM"
        seed_smiles_opt = True
        if "P5_small_molecule" not in branches:
            branches.append("P5_small_molecule")

    return {
        "symbol": symbol,
        "primary": primary,
        "secondary": secondary,
        "branches": branches,
        "modality_scores": {k: round(v, 3) for k, v in scores.items()},
        "repurposing_priority": repurposing_priority,
        "seed_smiles_opt": seed_smiles_opt,
        "greyzone_resolved": greyzone,
        "concerns": concerns,
    }


def _rank(scores: Dict[str, float]) -> Tuple[str, Optional[str]]:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0] if ranked and ranked[0][1] > 0 else "none"
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > _SECONDARY_CUTOFF else None
    return primary, secondary


def _is_greyzone(scores: Dict[str, float], target: Dict, gof_hint: bool) -> bool:
    ordered = sorted(scores.values(), reverse=True)
    close = len(ordered) >= 2 and ordered[0] > 0 and (ordered[0] - ordered[1]) < _GREYZONE_DELTA
    drug = target.get("max_druggability", 0.0)
    borderline = 0.45 <= drug <= 0.55
    return bool(close or borderline or gof_hint)


def _llm_greyzone(symbol, scores, target, gof_hint, provider, db, run_id) -> Optional[Dict]:
    loc = target.get("localization", {})
    prompt = (
        f"Choose the single best drug modality for target {symbol}. Borderline case.\n\n"
        f"Modality scores: {scores}\n"
        f"Localization: {loc.get('compartment')} "
        f"(membrane={loc.get('is_membrane')}, secreted={loc.get('is_secreted')})\n"
        f"Max druggability: {target.get('max_druggability')}\n"
        f"Gain-of-function hint: {gof_hint}\n"
        f"ChEMBL potent compounds: {target.get('chembl', {}).get('n_potent')}\n\n"
        "Options: SM, PROTAC, AB, peptide, oligo. A gain-of-function intracellular "
        "target with a weak pocket usually favours PROTAC degradation over inhibition. "
        "Return your decision, a confidence 0-1, and any concerns."
    )
    try:
        result = provider.complete(prompt, schema=ModalityGreyzone, temperature=0.1)
    except Exception as exc:
        log.warning("[3] %s greyzone gate failed: %s", symbol, exc)
        return None
    if not result.parsed:
        return None
    if db:
        log_decision(db, run_id=run_id, phase=3, gate="3_modality_greyzone",
                     provider=provider.name, model=provider.model,
                     prompt=prompt, raw_response=result.text, decision_json=result.parsed)
    return result.parsed


def _repurposing_priority(max_phase: int) -> str:
    if max_phase >= 4:
        return "HIGH"
    if max_phase in (2, 3):
        return "MEDIUM"
    if max_phase == 1:
        return "LOW_CLINICAL"
    return "LOW"


def _branches(intent_mode: str, primary: str, secondary: Optional[str],
              repurposing_priority: str, novelty_mode: bool) -> List[str]:
    branches: List[str] = []
    denovo_primary = _DENOVO_PHASE.get(primary)

    if intent_mode == "repurpose":
        # Phase 4 only, no de-novo branch.
        return ["P4_repurpose"]

    if intent_mode == "de_novo":
        if denovo_primary:
            branches.append(denovo_primary)
        return branches

    # explore: Phase 4 always + primary de-novo branch.
    branches.append("P4_repurpose")
    if denovo_primary:
        branches.append(denovo_primary)
    if secondary:
        sec = _DENOVO_PHASE.get(secondary)
        if sec and sec not in branches:
            branches.append(sec)
    return branches
