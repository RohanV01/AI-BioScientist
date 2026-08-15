"""
Phase 8 — In-Silico Validation Gate runner.

For each target: take top-5 candidates from Phase 7 (or Phase 4/5/6 if P7 skipped),
re-dock at high exhaustiveness (12), compute the final 6-axis scorecard,
generate a medicinal-chemist brief via LLM, and mark passed/failed.

Binding is confirmed by triple Vina re-docking (3 independent runs) + score CV.
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

from .scorecard import compute_final_score, rank_final_candidates

log = logging.getLogger(__name__)

_TOP_CANDIDATES_PER_TARGET = int(os.environ.get("P8_TOP_N", "5"))
_REDOCK_EXHAUSTIVENESS     = int(os.environ.get("P8_EXHAUSTIVENESS", "12"))
_REDOCK_RUNS               = 3   # triple run for pose stability estimate
_DOCK_WORKERS              = int(os.environ.get("P8_WORKERS", "4"))


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_phase8(
    run_id: str,
    config: RunConfig,
    db,
    phase7_output: Optional[Dict],
    phase4_output: Optional[Dict],
    phase2_output: Optional[Dict],
    phase3_output: Optional[Dict],
) -> Dict[str, Any]:
    t_start = time.monotonic()
    try:
        return _run_phase8_body(
            run_id=run_id, config=config, db=db,
            phase7_output=phase7_output, phase4_output=phase4_output,
            phase2_output=phase2_output, phase3_output=phase3_output,
            t_start=t_start,
        )
    except Exception as exc:
        log.exception("[Phase 8] Failed for run %s", run_id)
        try:
            run_state.mark_phase_failed(db, run_id, phase=8, error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise


def _run_phase8_body(
    run_id: str, config: RunConfig, db,
    phase7_output: Optional[Dict], phase4_output: Optional[Dict],
    phase2_output: Optional[Dict], phase3_output: Optional[Dict],
    t_start: float,
) -> Dict[str, Any]:
    provider = _make_provider(config)

    p2_by_symbol: Dict[str, Dict] = {
        t["symbol"]: t for t in (phase2_output or {}).get("validated_targets", [])
    }
    p3_routing: Dict[str, str] = {
        r["symbol"]: r.get("primary", "SM")
        for r in (phase3_output or {}).get("routing", [])
    }

    # Gather top candidates per target from P7 (or P4/5/6 direct)
    all_candidates_by_target = _gather_candidates(
        phase7_output=phase7_output,
        phase4_output=phase4_output,
        db=db,
        run_id=run_id,
    )
    log.info("[Phase 8] Validating %d targets", len(all_candidates_by_target))

    if not all_candidates_by_target:
        out = _empty_output(t_start)
        run_state.mark_phase_completed(db, run_id, phase=8, output=out)
        return out

    validated_results: Dict[str, Dict] = {}
    total_pass = 0

    for symbol, candidates in all_candidates_by_target.items():
        p2 = p2_by_symbol.get(symbol, {})
        p3_primary = p3_routing.get(symbol, "SM")
        t0 = time.monotonic()
        log.info("[8] → %s (%d candidates)", symbol, len(candidates))

        try:
            result = _validate_one(
                symbol=symbol,
                candidates=candidates[:_TOP_CANDIDATES_PER_TARGET],
                p2=p2,
                p3_primary=p3_primary,
                config=config,
                provider=provider,
                db=db,
                run_id=run_id,
            )
        except Exception as exc:
            log.error("[8] %s failed: %s", symbol, exc, exc_info=True)
            result = {"candidates": candidates[:_TOP_CANDIDATES_PER_TARGET],
                      "n_passed": 0, "error": str(exc)}

        validated_results[symbol] = result
        n_pass = result.get("n_passed", 0)
        total_pass += n_pass
        log.info("[8] %s: %d/%d passed (%.1fs)",
                 symbol, n_pass, len(candidates[:_TOP_CANDIDATES_PER_TARGET]),
                 time.monotonic() - t0)

    wall_time = round(time.monotonic() - t_start, 1)
    output = {
        "validation": validated_results,
        "n_targets": len(all_candidates_by_target),
        "n_candidates_passed": total_pass,
        "wall_time_s": wall_time,
    }
    log.info("[Phase 8] Validation complete: %d candidates passed across %d targets (%.1fs)",
             total_pass, len(all_candidates_by_target), wall_time)
    return output


# ─────────────────────────────────────────────────────────────────────────────
# Per-target validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_one(
    *,
    symbol: str,
    candidates: List[Dict],
    p2: Dict,
    p3_primary: str,
    config: RunConfig,
    provider,
    db,
    run_id: str,
) -> Dict:
    pdb_url: Optional[str] = p2.get("structure", {}).get("pdb_url")
    pockets: List[Dict] = p2.get("pockets", [])
    best_pocket: Optional[Dict] = pockets[0] if pockets else None

    # Re-dock SM candidates at higher exhaustiveness (3 independent runs)
    redocked = _redock_candidates(
        candidates=candidates,
        pdb_url=pdb_url,
        pocket=best_pocket,
        symbol=symbol,
        exhaustiveness=_REDOCK_EXHAUSTIVENESS,
        n_runs=_REDOCK_RUNS,
    )

    # Score each candidate
    scored = []
    for c in candidates:
        smi = c.get("smiles", "")
        vina_runs = redocked.get(smi) if smi else None  # list of 3 scores or None
        vina_best = min(vina_runs) if vina_runs else c.get("vina_score")

        c_scored = dict(c)
        c_scored["vina_score_final"] = vina_best
        c_scored["vina_runs"] = vina_runs

        scorecard = compute_final_score(
            candidate=c_scored,
            vina_runs=vina_runs,
            selectivity_target=config.selectivity_target,
            p3_primary=p3_primary,
            indication_type=config.indication_type,
        )
        c_scored.update(scorecard)
        scored.append(c_scored)

    ranked = rank_final_candidates(scored)
    passed = [c for c in ranked if c.get("passed")]
    failed = [c for c in ranked if not c.get("passed")]

    # LLM brief for passed candidates
    for c in passed:
        try:
            c["candidate_brief"] = _gate_candidate_brief(
                provider=provider, db=db, run_id=run_id,
                symbol=symbol, candidate=c, config=config,
            )
        except Exception as exc:
            log.debug("[8.3] brief gate failed: %s", exc)
            c["candidate_brief"] = ""

    # Update DB
    _update_candidates_final(db, run_id, symbol, ranked)

    return {
        "candidates": ranked,
        "n_passed": len(passed),
        "n_failed": len(failed),
        "target_validation_score": round(
            sum(c.get("combined_score", 0) for c in ranked) / max(1, len(ranked)), 4
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Re-docking
# ─────────────────────────────────────────────────────────────────────────────

def _redock_candidates(
    candidates: List[Dict],
    pdb_url: Optional[str],
    pocket: Optional[Dict],
    symbol: str,
    exhaustiveness: int = 12,
    n_runs: int = 3,
) -> Dict[str, List[float]]:
    """
    Re-dock each SM candidate n_runs times for pose stability estimation.
    Returns {smiles: [score_run1, score_run2, score_run3]}.
    Biologics (no SMILES) are skipped.
    """
    import tempfile, shutil
    from pathlib import Path

    sm_candidates = [c for c in candidates
                     if c.get("smiles") and c.get("_kind", "sm") in ("sm", "de_novo_sm", "repurposing", "")]
    results: Dict[str, List[float]] = {}

    if not sm_candidates or not pdb_url or not pocket or not pocket.get("cx"):
        return results

    tmp = Path(tempfile.mkdtemp(prefix=f"rxdis_p8_{symbol}_"))
    try:
        from src.phases.phase4.docking import (
            check_structure_quality, dock_library, prepare_receptor_pdbqt,
        )
        receptor_pdbqt = prepare_receptor_pdbqt(pdb_url, tmp)
        if not receptor_pdbqt:
            return results

        for run_idx in range(n_runs):
            run_dir = tmp / f"run{run_idx}"
            run_dir.mkdir(exist_ok=True)
            cand_dicts = [{"smiles": c["smiles"], "drug_name": f"P8_{i}"}
                          for i, c in enumerate(sm_candidates)]
            docked = dock_library(
                candidates=cand_dicts,
                receptor_pdbqt=receptor_pdbqt,
                pocket=pocket,
                work_dir=run_dir,
                exhaustiveness=exhaustiveness,
                n_workers=_DOCK_WORKERS,
            )
            for d in docked:
                smi = d.get("smiles", "")
                score = d.get("vina_score")
                if smi and score is not None:
                    results.setdefault(smi, []).append(score)

        n_docked = sum(1 for v in results.values() if len(v) >= 1)
        log.info("[8.dock] %s: %d/%d molecules re-docked (%d runs)",
                 symbol, n_docked, len(sm_candidates), n_runs)

    except Exception as exc:
        log.warning("[8.dock] %s: re-docking failed — %s", symbol, exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# LLM gate: candidate brief
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _gate_candidate_brief(
    *, provider, db, run_id: str, symbol: str, candidate: Dict, config: RunConfig,
) -> str:
    subs = candidate.get("subscores", {})
    prompt = (
        f"You are a medicinal chemist writing a drug candidate report.\n\n"
        f"Target: {symbol}\n"
        f"Indication: {config.indication_type}\n"
        f"Candidate: {candidate.get('smiles') or candidate.get('sequence', 'unknown')}\n"
        f"Kind: {candidate.get('kind', candidate.get('_kind', 'unknown'))}\n"
        f"Combined score: {candidate.get('combined_score')}\n"
        f"Subscores: binding={subs.get('binding_affinity')}, "
        f"stability={subs.get('pose_stability')}, "
        f"ADMET={subs.get('admet_or_developability')}, "
        f"selectivity={subs.get('selectivity')}, "
        f"novelty={subs.get('novelty')}\n"
        f"Write a 4-sentence medicinal chemist brief covering: "
        f"(1) why this candidate looks promising for {symbol}, "
        f"(2) its key strengths vs standard-of-care, "
        f"(3) the biggest risk or caveat, "
        f"(4) recommended first wet-lab experiment.\n\n"
        f'Return ONLY: {{"title": "...", "verdict": "promising", '
        f'"evidence": ["..."], "risks": ["..."], "next_wetlab_experiment": "..."}}'
    )
    result = provider.complete(prompt, temperature=0.2, max_tokens=350)
    parsed = _extract_json(result.text)

    if parsed:
        brief = (
            f"{parsed.get('title', '')}. "
            f"Verdict: {parsed.get('verdict', '')}. "
            f"Evidence: {'; '.join(parsed.get('evidence', []))}. "
            f"Risks: {'; '.join(parsed.get('risks', []))}. "
            f"Next step: {parsed.get('next_wetlab_experiment', '')}"
        )
    else:
        brief = result.text[:400]

    run_state.log_decision(
        db, run_id=run_id, phase=8,
        gate=f"8.3_brief_{symbol}",
        provider=provider.name,
        model=getattr(provider, "model", "unknown"),
        prompt=prompt, raw_response=result.text,
        decision_json=parsed or {"raw": brief},
    )
    return brief


# ─────────────────────────────────────────────────────────────────────────────
# Candidate gathering + DB
# ─────────────────────────────────────────────────────────────────────────────

def _gather_candidates(
    phase7_output: Optional[Dict],
    phase4_output: Optional[Dict],
    db,
    run_id: str,
) -> Dict[str, List[Dict]]:
    """
    Collect top candidates per target.
    Priority: P7 Pareto front > P4 repurposing > DB query.
    """
    result: Dict[str, List[Dict]] = {}

    # P7 Pareto front
    if phase7_output:
        for symbol, opt in phase7_output.get("optimized", {}).items():
            front = opt.get("pareto_front", [])
            if front:
                result[symbol] = front

    # P4 repurposing (for repurpose-only runs)
    if phase4_output:
        for symbol, cands in phase4_output.get("repurposing", {}).items():
            if symbol not in result:
                result[symbol] = cands

    # Fallback: query DB candidates table
    if not result:
        try:
            resp = (db.table("candidates")
                    .select("*")
                    .eq("run_id", run_id)
                    .order("combined_score", desc=True)
                    .execute())
            if resp.data:
                for row in resp.data:
                    sym = row.get("target_id", "")
                    if sym:
                        cand = {
                            "smiles": row.get("smiles", ""),
                            "combined_score": row.get("combined_score", 0),
                            "kind": row.get("kind", ""),
                            **row.get("subscores", {}),
                        }
                        result.setdefault(sym, []).append(cand)
        except Exception as exc:
            log.warning("[8] DB candidate query failed: %s", exc)

    return result


def _update_candidates_final(db, run_id: str, symbol: str, candidates: List[Dict]) -> None:
    """Update combined_score and subscores in DB for P8 final scores."""
    for c in candidates:
        cid = c.get("chembl_id") or c.get("id") or c.get("smiles", "")[:30]
        try:
            db.table("candidates") \
              .update({
                  "combined_score": c.get("combined_score"),
                  "subscores": {
                      **c.get("subscores", {}),
                      "phase": 8,
                      "final_rank": c.get("final_rank"),
                      "passed": c.get("passed"),
                      "candidate_brief": c.get("candidate_brief", ""),
                  },
              }) \
              .eq("run_id", run_id) \
              .eq("target_id", symbol) \
              .execute()
        except Exception as exc:
            log.debug("[8] DB update failed for %s/%s: %s", symbol, cid, exc)


def _make_provider(config: RunConfig):
    from src.llm.factory import make_provider
    return make_provider(config.llm)


def _empty_output(t_start: float) -> Dict:
    return {
        "validation": {},
        "n_targets": 0,
        "n_candidates_passed": 0,
        "note": "No candidates to validate",
        "wall_time_s": round(time.monotonic() - t_start, 1),
    }
