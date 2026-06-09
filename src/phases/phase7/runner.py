"""
Phase 7 — Multi-Parameter Lead Optimization (MPO) runner.

Active-learning loop:
  1. Build initial candidate set from Phase 5 (SM) + Phase 6 (biologic)
  2. Fit multi-objective GP surrogate on initial evaluations
  3. Suggest 20 new candidates per iteration via UCB acquisition
  4. Re-evaluate (re-dock + re-ADMET for SM; re-developability for biologics)
  5. Update GP and Pareto front
  6. Convergence: hypervolume improvement <1% OR 5 iterations OR budget exhausted

Objectives (all maximised, normalised 0-1):
  potency          — Vina norm / developability_score
  admet_score      — ADMET / developability
  novelty          — 1 - max_tanimoto
  selectivity      — absence of off-target flags (1.0 default when no selectivity_target)

Output: augmented candidate dicts with pareto_rank, desirability, objectives.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from src.config.run_config import RunConfig
from src.db import run_state

from .gp_surrogate import MultiObjectiveSurrogate
from .pareto import compute_desirability, compute_hypervolume, compute_pareto_front

log = logging.getLogger(__name__)

_MAX_ITERATIONS = int(os.environ.get("P7_MAX_ITER", "5"))
_N_SUGGEST      = int(os.environ.get("P7_N_SUGGEST", "20"))
_HV_THRESHOLD   = float(os.environ.get("P7_HV_THRESHOLD", "0.01"))

_OBJECTIVES_SM  = ["potency", "admet_score", "novelty"]
_OBJECTIVES_BIO = ["developability_score", "novelty_bio"]


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_phase7(
    run_id: str,
    config: RunConfig,
    db,
    phase5_output: Optional[Dict],
    phase6_output: Optional[Dict],
    phase2_output: Optional[Dict] = None,
    phase3_output: Optional[Dict] = None,
) -> Dict[str, Any]:
    from src.phases.base_runner import PhaseGuard
    t_start = time.monotonic()
    with PhaseGuard(db, run_id, phase=7, config=config) as guard:
        guard.check_budget()
        return _run_phase7_body(
            run_id=run_id, config=config, db=db,
            phase5_output=phase5_output,
            phase6_output=phase6_output,
            phase2_output=phase2_output,
            phase3_output=phase3_output,
            t_start=t_start,
        )


def _run_phase7_body(
    run_id: str, config: RunConfig, db,
    phase5_output: Optional[Dict], phase6_output: Optional[Dict],
    phase2_output: Optional[Dict], phase3_output: Optional[Dict],
    t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    # Gather all candidates from P5 + P6
    sm_candidates = _collect_sm_candidates(phase5_output)
    bio_candidates = _collect_bio_candidates(phase6_output)
    all_targets = set(
        list(sm_candidates.keys()) + list(bio_candidates.keys())
    )
    log.info("[Phase 7] MPO: %d SM targets, %d bio targets",
             len(sm_candidates), len(bio_candidates))

    if not all_targets:
        out = _empty_output(t_start)
        run_state.mark_phase_completed(db, run_id, phase=7, output=out)
        return out

    optimized_results: Dict[str, Dict] = {}
    total_candidates = 0

    for symbol in all_targets:
        sm = sm_candidates.get(symbol, [])
        bio = bio_candidates.get(symbol, [])
        try:
            opt = _optimize_one(
                symbol=symbol,
                sm_candidates=sm,
                bio_candidates=bio,
                config=config,
                provider=provider,
                db=db,
                run_id=run_id,
            )
        except Exception as exc:
            log.error("[7] %s failed: %s", symbol, exc, exc_info=True)
            opt = _fallback_optimize(symbol, sm, bio)

        optimized_results[symbol] = opt
        total_candidates += len(opt.get("pareto_front", []))
        _update_candidates_db(db, run_id, symbol, opt)

    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "optimized": optimized_results,
        "n_targets": len(all_targets),
        "n_pareto_total": total_candidates,
        "wall_time_s": wall_time,
    }
    run_state.mark_phase_completed(db, run_id, phase=7, output=output)
    run_state.log_compute(db, run_id=run_id, phase=7, step="phase7_complete",
                          service="local", wall_time_s=wall_time)
    log.info("[Phase 7] Complete: %d Pareto candidates across %d targets (%.1fs)",
             total_candidates, len(all_targets), wall_time)
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Per-target optimization
# ─────────────────────────────────────────────────────────────────────────────

def _optimize_one(
    *,
    symbol: str,
    sm_candidates: List[Dict],
    bio_candidates: List[Dict],
    config: RunConfig,
    provider,
    db,
    run_id: str,
) -> Dict:
    """Run the active-learning MPO loop for one target."""

    # Normalise candidates to a unified objective space
    all_cands = _normalise_sm(sm_candidates) + _normalise_bio(bio_candidates)
    if not all_cands:
        return {"pareto_front": [], "iterations_run": 0, "hypervolume_final": 0.0}

    # Determine objective set
    has_sm  = bool(sm_candidates)
    obj_keys = _OBJECTIVES_SM if has_sm else _OBJECTIVES_BIO
    is_peptide = not has_sm

    surrogate = MultiObjectiveSurrogate(obj_keys)
    evaluated = list(all_cands)   # initially all P5/P6 candidates are "evaluated"
    pool = []                      # new suggestions to evaluate in each iteration

    prev_hv = 0.0
    iterations_run = 0

    for iteration in range(_MAX_ITERATIONS):
        # Fit GP on all evaluated candidates
        fitted = surrogate.fit(evaluated, is_peptide=is_peptide)

        # Compute Pareto front + hypervolume
        front, _ = compute_pareto_front(evaluated, obj_keys)
        hv = compute_hypervolume(front, obj_keys)
        hv_improvement = (hv - prev_hv) / max(1e-9, prev_hv) if prev_hv > 0 else 1.0
        log.info("[7] %s iter=%d hv=%.4f improvement=%.1f%%",
                 symbol, iteration, hv, hv_improvement * 100)

        # Convergence check
        if iterations_run > 0 and hv_improvement < _HV_THRESHOLD:
            log.info("[7] %s: hypervolume converged (improvement=%.2f%%)",
                     symbol, hv_improvement * 100)
            break

        # Budget check
        budget_usd = config.budget_hosted_usd
        if budget_usd <= 0:
            log.info("[7] %s: hosted budget exhausted", symbol)
            break

        # LLM gate: iteration review
        if fitted and iteration > 0:
            try:
                _gate_iteration_review(
                    provider=provider, db=db, run_id=run_id,
                    symbol=symbol, iteration=iteration,
                    evaluated=evaluated, hv=hv, obj_keys=obj_keys,
                )
            except Exception as exc:
                log.debug("[7.gate] %s: %s", symbol, exc)

        # Suggest new candidates from existing pool using GP
        if fitted and pool:
            suggestions = surrogate.suggest(pool, n_suggest=_N_SUGGEST,
                                            is_peptide=is_peptide)
            # Re-evaluate suggestions (for SM: re-score descriptors; for bio: re-developability)
            new_eval = _re_evaluate(suggestions, symbol=symbol, config=config,
                                    is_peptide=is_peptide)
            evaluated.extend(new_eval)
            pool = [p for p in pool if p not in suggestions]
        else:
            # Generate new pool from BRICS/mutations on the Pareto front
            pool = _generate_pool(front, symbol, is_peptide=is_peptide)
            evaluated.extend(_re_evaluate(pool[:_N_SUGGEST], symbol=symbol,
                                          config=config, is_peptide=is_peptide))
            pool = pool[_N_SUGGEST:]

        prev_hv = hv
        iterations_run += 1

    # Final Pareto front
    final_front, dominated = compute_pareto_front(evaluated, obj_keys)
    for c in final_front:
        c["desirability"] = compute_desirability(c, obj_keys)
    final_front.sort(key=lambda c: c["desirability"], reverse=True)
    for i, c in enumerate(final_front):
        c["pareto_rank"] = i + 1

    hv_final = compute_hypervolume(final_front, obj_keys)
    return {
        "pareto_front": final_front[:20],
        "iterations_run": iterations_run,
        "hypervolume_final": round(hv_final, 4),
        "n_evaluated_total": len(evaluated),
    }


def _fallback_optimize(symbol: str, sm: List[Dict], bio: List[Dict]) -> Dict:
    """Fallback when active-learning fails: return top candidates by existing score."""
    all_cands = sorted(
        _normalise_sm(sm) + _normalise_bio(bio),
        key=lambda c: c.get("desirability", 0.0),
        reverse=True,
    )
    for i, c in enumerate(all_cands[:20]):
        c["pareto_rank"] = i + 1
        c["desirability"] = c.get("desirability", 0.0)
    return {
        "pareto_front": all_cands[:20],
        "iterations_run": 0,
        "hypervolume_final": 0.0,
        "note": "fallback_no_optimization",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Candidate normalisation (map P5/P6 outputs → unified objective space)
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_sm(candidates: List[Dict]) -> List[Dict]:
    """Map P5 de_novo_sm candidates to objective space."""
    result = []
    for c in candidates:
        obj = dict(c)
        obj["potency"]    = float(c.get("vina_norm") or 0.0)
        obj["admet_score"] = float(c.get("admet_score") or 0.5)
        obj["novelty"]    = float(c.get("novelty") or 0.0)
        obj["desirability"] = (
            0.4 * obj["potency"] + 0.3 * obj["admet_score"] + 0.3 * obj["novelty"]
        )
        obj["_kind"] = "sm"
        result.append(obj)
    return result


def _normalise_bio(candidates: List[Dict]) -> List[Dict]:
    """Map P6 biologic candidates to objective space."""
    result = []
    for c in candidates:
        obj = dict(c)
        obj["developability_score"] = float(c.get("developability_score") or 0.0)
        obj["novelty_bio"] = 1.0   # biologics are inherently novel vs small drugs
        obj["desirability"] = (
            0.6 * obj["developability_score"] + 0.4 * obj["novelty_bio"]
        )
        obj["_kind"] = "biologic"
        result.append(obj)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Re-evaluation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _re_evaluate(
    candidates: List[Dict],
    symbol: str,
    config: RunConfig,
    is_peptide: bool,
) -> List[Dict]:
    """
    Re-score candidates. For SM: re-run ADMET + update descriptors.
    For biologics: re-run developability.
    """
    if not candidates:
        return []

    if is_peptide:
        from src.phases.phase6.developability import score_developability
        result = []
        for c in candidates:
            seq = c.get("sequence", "")
            if not seq:
                result.append(c)
                continue
            dev = score_developability(
                seq,
                target_class=c.get("target_class", "extracellular"),
                indication_type=config.indication_type,
            )
            c_new = dict(c)
            c_new.update({
                "developability_score": dev["developability_score"],
                "novelty_bio": 1.0,
                "desirability": 0.6 * dev["developability_score"] + 0.4,
            })
            result.append(c_new)
        return result
    else:
        from src.phases.phase5.admet import score_admet
        result = []
        for c in candidates:
            smi = c.get("smiles", "")
            if not smi:
                result.append(c)
                continue
            admet = score_admet(smi, indication_type=config.indication_type)
            c_new = dict(c)
            c_new.update({
                "admet_score": admet.get("admet_score", 0.5),
                "potency": float(c.get("vina_norm") or 0.0),
                "novelty": float(c.get("novelty") or 0.0),
                "desirability": (
                    0.4 * float(c.get("vina_norm") or 0)
                    + 0.3 * admet.get("admet_score", 0.5)
                    + 0.3 * float(c.get("novelty") or 0)
                ),
            })
            result.append(c_new)
        return result


def _generate_pool(
    pareto_front: List[Dict],
    symbol: str,
    is_peptide: bool,
    n_pool: int = 100,
) -> List[Dict]:
    """Generate a new candidate pool for the next iteration."""
    if is_peptide:
        return _mutate_peptides(pareto_front, n_mutations=n_pool)
    else:
        return _enumerate_sm_analogs(pareto_front, n_analogs=n_pool)


def _mutate_peptides(front: List[Dict], n_mutations: int = 100) -> List[Dict]:
    """Single-residue substitution mutations on Pareto-front peptides."""
    import random
    AA = "ACDEFGHIKLMNPQRSTVWY"
    mutations = []
    for c in front:
        seq = c.get("sequence", "")
        if not seq:
            continue
        for _ in range(n_mutations // max(1, len(front))):
            pos = random.randint(0, len(seq) - 1)
            new_aa = random.choice(AA)
            new_seq = seq[:pos] + new_aa + seq[pos + 1:]
            mutations.append({
                **c,
                "sequence": new_seq,
                "parent": seq,
                "_mutation": f"{seq[pos]}{pos+1}{new_aa}",
            })
    return mutations[:n_mutations]


def _enumerate_sm_analogs(front: List[Dict], n_analogs: int = 100) -> List[Dict]:
    """BRICS-based analog enumeration from Pareto-front SMILES."""
    try:
        seed_smiles = [c["smiles"] for c in front if c.get("smiles")]
        from src.phases.phase5.fragment_gen import generate_with_brics
        new_smiles = generate_with_brics(seed_smiles, n_generate=n_analogs)
        base = front[0] if front else {}
        return [{**base, "smiles": smi, "parent": seed_smiles[0] if seed_smiles else ""}
                for smi in new_smiles[:n_analogs]]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# LLM gate
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _gate_iteration_review(
    *, provider, db, run_id: str, symbol: str,
    iteration: int, evaluated: List[Dict], hv: float, obj_keys: List[str],
) -> None:
    top = sorted(evaluated, key=lambda c: c.get("desirability", 0), reverse=True)[:5]
    top_smiles = [c.get("smiles") or c.get("sequence", "") for c in top]
    prompt = (
        f"You are reviewing a Bayesian optimisation run for drug discovery.\n\n"
        f"Target: {symbol}\n"
        f"Iteration: {iteration}\n"
        f"Objectives: {obj_keys}\n"
        f"Hypervolume: {hv:.4f}\n"
        f"Top-5 candidates: {top_smiles}\n"
        f"Total evaluated: {len(evaluated)}\n\n"
        f"Assess: (1) what chemical/sequence space is being explored, "
        f"(2) explore vs exploit balance, "
        f"(3) any unreasonable suggestions to flag.\n\n"
        f'Return ONLY: {{"space_explored": "...", "balance_assessment": "...", '
        f'"flagged_unreasonable": [], "recommendation": "..."}}'
    )
    try:
        result = provider.complete(prompt, temperature=0.2, max_tokens=300)
        parsed = _extract_json(result.text)
        run_state.log_decision(
            db, run_id=run_id, phase=7,
            gate=f"7.2_iteration_review_{symbol}_iter{iteration}",
            provider=provider.name,
            model=getattr(provider, "model", "unknown"),
            prompt=prompt, raw_response=result.text,
            decision_json=parsed or {},
        )
    except Exception as exc:
        log.debug("[7.gate] %s iter=%d: %s", symbol, iteration, exc)


# ─────────────────────────────────────────────────────────────────────────────
# DB update + helpers
# ─────────────────────────────────────────────────────────────────────────────

def _update_candidates_db(db, run_id: str, symbol: str, opt: Dict) -> None:
    """Update candidate subscores with pareto_rank + desirability."""
    for c in opt.get("pareto_front", []):
        cid = c.get("chembl_id") or c.get("id") or c.get("smiles", "")[:20]
        try:
            db.table("candidates") \
              .update({"subscores": {
                  **c,
                  "pareto_rank": c.get("pareto_rank"),
                  "desirability": c.get("desirability"),
                  "iterations_run": opt.get("iterations_run"),
              }}) \
              .eq("run_id", run_id) \
              .eq("target_id", symbol) \
              .execute()
        except Exception as exc:
            log.debug("[7] DB update failed for %s/%s: %s", symbol, cid, exc)


def _collect_sm_candidates(phase5_output: Optional[Dict]) -> Dict[str, List[Dict]]:
    if not phase5_output:
        return {}
    return phase5_output.get("de_novo_sm", {})


def _collect_bio_candidates(phase6_output: Optional[Dict]) -> Dict[str, List[Dict]]:
    if not phase6_output:
        return {}
    return phase6_output.get("biologic", {})


def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)


def _empty_output(t_start: float) -> Dict:
    return {
        "optimized": {},
        "n_targets": 0,
        "n_pareto_total": 0,
        "note": "No P5/P6 candidates to optimize",
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }
