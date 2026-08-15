"""
Phase 1.8 — Aggregate scoring and ranked list construction.
Weights adjusted by indication_type via LLM gate 1.8_weight_tuning.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Tuple

from src.llm.provider import LLMProvider
from src.db.run_state import log_decision
from .schemas import ScoringWeights

log = logging.getLogger(__name__)

_DEFAULT_WEIGHTS = {
    "ot_assoc": 0.30,
    "literature": 0.15,
    "genetic": 0.15,
    "ppi_eigenvector": 0.10,
    "pathway": 0.10,
    "tractability": 0.10,
    "novelty": 0.10,
}


def tune_weights(
    indication_type: str,
    provider: LLMProvider,
    db,
    run_id: str,
) -> Dict[str, float]:
    """
    LLM gate 1.8 — let the LLM adjust weights for the indication type.
    Uses self-consistency (2 rounds) for small local models.
    """
    rounds = provider.self_consistency_rounds(critical=True)
    results: List[Dict] = []

    for _ in range(rounds):
        prompt = (
            f"You are adjusting scoring weights for a drug target discovery pipeline.\n"
            f"Indication type: '{indication_type}'\n\n"
            f"Default weights (must sum to 1.0):\n"
            + "\n".join(f"  {k}: {v}" for k, v in _DEFAULT_WEIGHTS.items())
            + f"\n\nAdjust these weights to best reflect the priorities for '{indication_type}' drug discovery. "
            f"For oncology: genetic evidence and novelty matter more; for chronic: safety (tractability) and "
            f"literature evidence matter more; for acute: network centrality matters more.\n"
            f"Return the adjusted weights and a one-sentence reasoning."
        )
        result = provider.complete(prompt, schema=ScoringWeights, temperature=0.1)
        if result.parsed:
            results.append(result.parsed)

    if not results:
        log.info("[1.8] Weight tuning LLM failed, using defaults")
        return _DEFAULT_WEIGHTS

    # Average across self-consistency rounds
    final = _average_weights([r for r in results if r])
    _normalize_weights(final)

    if db:
        log_decision(
            db,
            run_id=run_id,
            phase=1,
            gate="1.8_weight_tuning",
            provider=provider.name,
            model=provider.model,
            prompt="weight_tuning",
            raw_response=str(results),
            decision_json=final,
        )

    log.info("[1.8] Tuned weights for '%s': %s", indication_type, final)
    return final


def _average_weights(results: List[Dict]) -> Dict[str, float]:
    keys = list(_DEFAULT_WEIGHTS.keys())
    averaged = {}
    for k in keys:
        vals = [r.get(k, _DEFAULT_WEIGHTS[k]) for r in results]
        averaged[k] = sum(vals) / len(vals)
    return averaged


def _normalize_weights(w: Dict[str, float]) -> None:
    total = sum(w.values())
    if total <= 0:
        w.update(_DEFAULT_WEIGHTS)
        return
    for k in w:
        w[k] = round(w[k] / total, 4)


def score_and_rank(
    targets: List[Dict],
    lit_map: Dict[str, Dict],
    genetic_map: Dict[str, Dict],
    ppi_map: Dict[str, Dict],
    pathway_map: Dict[str, Dict],
    tdl_map: Dict[str, Dict],
    weights: Dict[str, float],
    target_count_max: int,
    seed_targets: set,
    exclude_targets: set,
) -> List[Dict]:
    """
    Compute aggregate score and return ranked list of targets.
    seed_targets always appear; exclude_targets are removed before scoring.
    """
    # Novelty score: Tdark=1.0, Tbio=0.6, Tchem=0.3, Tclin=0.0
    _NOVELTY = {"Tdark": 1.0, "Tbio": 0.6, "Tchem": 0.3, "Tclin": 0.0}

    scored = []
    for t in targets:
        sym = t["symbol"]
        ensembl = t["ensembl_id"]

        if sym in exclude_targets or ensembl in exclude_targets:
            continue

        # Gather subscores
        ot_score = t.get("ot_assoc_score", 0.0)
        lit_score = lit_map.get(sym, {}).get("literature_score", 0.0)
        gen_data = genetic_map.get(sym, {})
        gen_score = gen_data.get("genetic_score", 0.0)
        ppi_data = ppi_map.get(sym, {})
        ppi_score = ppi_data.get("ppi_eigenvector_score", 0.0)
        path_data = pathway_map.get(sym, {})
        path_score = path_data.get("pathway_score", 0.0)
        tract_score = t.get("tractability_max", 0.0)
        tdl_info = tdl_map.get(sym, {"tdl": "Tbio"})
        novelty_score = _NOVELTY.get(tdl_info.get("tdl", "Tbio"), 0.6)

        # Hub penalty (broad hubs are deprioritised)
        hub_penalty = 0.0
        if ppi_data.get("is_hub") and not (sym in seed_targets or ensembl in seed_targets):
            hub_penalty = 0.05

        aggregate = (
            weights.get("ot_assoc", 0.30) * ot_score
            + weights.get("literature", 0.15) * lit_score
            + weights.get("genetic", 0.15) * gen_score
            + weights.get("ppi_eigenvector", 0.10) * ppi_score
            + weights.get("pathway", 0.10) * path_score
            + weights.get("tractability", 0.10) * tract_score
            + weights.get("novelty", 0.10) * novelty_score
            - hub_penalty
        )

        is_seeded = t.get("seeded", False) or sym in seed_targets or ensembl in seed_targets
        force_genetic = gen_data.get("force_include", False)

        scored.append({
            "symbol": sym,
            "ensembl_id": ensembl,
            "tdl": tdl_info.get("tdl", "Tbio"),
            "aggregate_score": round(max(0.0, aggregate), 4),
            "seeded": is_seeded,
            "force_genetic": force_genetic,
            "modality_hint": _modality_hint(tdl_info.get("tdl", "Tbio"), t.get("tractability_max", 0)),
            "evidence_trail": {
                "ot": round(ot_score, 4),
                "literature": round(lit_score, 4),
                "genetic": round(gen_score, 4),
                "ppi_eigenvector": round(ppi_score, 4),
                "pathway": round(path_score, 4),
                "tractability": round(tract_score, 4),
            },
            "ppi": ppi_data,
            "pathway": path_data,
            "genetic": gen_data,
        })

    # Sort: seeded/force-genetic always included, rest by aggregate_score descending
    forced = [t for t in scored if t["seeded"] or t["force_genetic"]]
    normal = [t for t in scored if not t["seeded"] and not t["force_genetic"]]
    normal.sort(key=lambda t: t["aggregate_score"], reverse=True)

    # Warn if top-20 signal is weak
    if normal and normal[19 if len(normal) > 19 else -1]["aggregate_score"] < 0.25:
        log.warning("[1.8] Top-20 aggregate score < 0.25: weak signal for this disease")

    # Merge, deduplicate, cap
    seen = set()
    ranked = []
    for t in (forced + normal):
        sym = t["symbol"]
        if sym not in seen:
            seen.add(sym)
            ranked.append(t)
        if len(ranked) >= target_count_max and not any(
            r["seeded"] or r["force_genetic"] for r in ranked[target_count_max:]
        ):
            break

    # Assign ranks
    for i, t in enumerate(ranked, start=1):
        t["rank"] = i

    log.info("[1.8] Ranked %d targets (max=%d)", len(ranked), target_count_max)
    return ranked[:target_count_max + len(forced)]


def _modality_hint(tdl: str, tractability_max: float) -> str:
    """Simple heuristic modality hint — Phase 3 will refine this properly."""
    if tdl == "Tclin":
        return "SM"   # Known clinical target → likely small molecule
    if tractability_max < 0.2:
        return "AB"   # Poor SM tractability → antibody
    return "SM"
