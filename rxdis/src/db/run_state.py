"""
Helpers for reading and writing run/phase state to Supabase.
All writes go through the service client (workers).
"""
from __future__ import annotations
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.utils.circuit_breaker import supabase_breaker

log = logging.getLogger(__name__)

# In-process cache for phase outputs within a Celery worker session.
# Key: (run_id, phase) → output dict. Avoids redundant DB reads when the same
# worker task calls get_phase_output multiple times for the same phase.
_output_cache: Dict[tuple, Optional[dict]] = {}
_cache_lock = threading.Lock()


def _cache_key(run_id: str, phase: int) -> tuple:
    return (run_id, phase)


def invalidate_output_cache(run_id: str) -> None:
    """Remove all cached outputs for a run (call when re-running a run)."""
    with _cache_lock:
        keys = [k for k in _output_cache if k[0] == run_id]
        for k in keys:
            del _output_cache[k]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_phase_running(db, run_id: str, phase: int) -> None:
    supabase_breaker.call(
        lambda: db.table("phase_results").upsert(
            {"run_id": run_id, "phase": phase, "status": "running", "started_at": _now()},
            on_conflict="run_id,phase",
        ).execute()
    )
    supabase_breaker.call(
        lambda: db.table("runs")
        .update({"current_phase": phase, "status": "running", "updated_at": _now()})
        .eq("id", run_id).execute()
    )


def mark_phase_completed(db, run_id: str, phase: int, output: dict, artifacts: list[str] | None = None) -> None:
    supabase_breaker.call(
        lambda: db.table("phase_results").upsert(
            {
                "run_id": run_id,
                "phase": phase,
                "status": "completed",
                "output_json": output,
                "artifact_paths": artifacts or [],
                "finished_at": _now(),
            },
            on_conflict="run_id,phase",
        ).execute()
    )
    with _cache_lock:
        _output_cache[_cache_key(run_id, phase)] = output


def mark_phase_failed(db, run_id: str, phase: int, error: str) -> None:
    with _cache_lock:
        _output_cache.pop(_cache_key(run_id, phase), None)
    try:
        supabase_breaker.call(
            lambda: db.table("phase_results").upsert(
                {"run_id": run_id, "phase": phase, "status": "failed",
                 "error": error, "finished_at": _now()},
                on_conflict="run_id,phase",
            ).execute()
        )
        supabase_breaker.call(
            lambda: db.table("runs")
            .update({"status": "failed", "updated_at": _now()})
            .eq("id", run_id).execute()
        )
    except Exception as exc:
        log.error("mark_phase_failed DB write failed for run %s phase %d: %s", run_id, phase, exc)


def get_phase_output(db, run_id: str, phase: int) -> Optional[dict]:
    key = _cache_key(run_id, phase)
    with _cache_lock:
        if key in _output_cache:
            return _output_cache[key]
    try:
        resp = (
            db.table("phase_results")
            .select("output_json")
            .eq("run_id", run_id)
            .eq("phase", phase)
            .eq("status", "completed")
            .single()
            .execute()
        )
        result = resp.data["output_json"] if resp.data else None
    except Exception as exc:
        log.warning("get_phase_output(%s, %d) failed: %s", run_id, phase, exc)
        return None
    with _cache_lock:
        _output_cache[key] = result
    return result


def log_decision(db, *, run_id: str, phase: int, gate: str, provider: str, model: str,
                 prompt: str, raw_response: str, decision_json: dict) -> None:
    db.table("decisions").insert({
        "run_id": run_id,
        "phase": phase,
        "gate": gate,
        "llm_provider": provider,
        "llm_model": model,
        "prompt": prompt,
        "raw_response": raw_response,
        "decision_json": decision_json,
    }).execute()


def log_compute(db, *, run_id: str, phase: int, step: str, service: str,
                cost_usd: float = 0.0, wall_time_s: float = 0.0) -> None:
    db.table("compute_log").insert({
        "run_id": run_id,
        "phase": phase,
        "step": step,
        "service": service,
        "cost_usd": cost_usd,
        "wall_time_s": wall_time_s,
    }).execute()


def update_target_validation(db, *, run_id: str, symbol: str, validation_score: float,
                             modality_primary: str, modality_secondary: Optional[str],
                             evidence_trail: dict) -> None:
    """Phase 2 — write validation results onto an existing target row (matched by symbol)."""
    db.table("targets").update({
        "validation_score": validation_score,
        "modality_primary": modality_primary,
        "modality_secondary": modality_secondary,
        "evidence_trail": evidence_trail,
    }).eq("run_id", run_id).eq("symbol", symbol).execute()


def update_target_routing(
    db,
    *,
    run_id: str,
    symbol: str,
    modality_primary: str,
    modality_secondary: Optional[str],
    branches: Optional[list] = None,
    repurposing_priority: Optional[str] = None,
) -> None:
    """Phase 3 — write final modality routing onto an existing target row."""
    update: dict = {
        "modality_primary": modality_primary,
        "modality_secondary": modality_secondary,
    }
    # Append Phase 3 routing details into evidence_trail via Supabase jsonb merge
    if branches is not None or repurposing_priority is not None:
        # Read current trail then merge (Supabase doesn't support nested jsonb merge in-place)
        try:
            row = (
                db.table("targets")
                .select("evidence_trail")
                .eq("run_id", run_id)
                .eq("symbol", symbol)
                .single()
                .execute()
                .data
            )
            trail = (row or {}).get("evidence_trail") or {}
            trail["phase3"] = {
                "branches": branches or [],
                "repurposing_priority": repurposing_priority or "LOW",
            }
            update["evidence_trail"] = trail
        except Exception:
            pass
    db.table("targets").update(update).eq("run_id", run_id).eq("symbol", symbol).execute()


def clear_targets(db, run_id: str) -> None:
    """Delete all target rows for a run. Phase 1 owns these rows, so it clears
    them once before (re)writing — this makes persistence independent of any
    unique(run_id,symbol) constraint (which may not exist in the DB) and makes
    re-runs idempotent."""
    db.table("targets").delete().eq("run_id", run_id).execute()


def insert_candidate(
    db,
    run_id: str,
    *,
    symbol: str,
    phase: int,
    kind: str,
    candidate_id: str,
    name: str,
    smiles: str,
    score: float,
    rank: int,
    passed: bool,
    evidence: dict,
) -> None:
    """Insert a candidate molecule/biologic into the candidates table.
    Called by Phases 4–6 runners after candidate generation/screening.
    """
    subscores = {
        **evidence,
        "rank": rank,
        "passed": passed,
        "phase": phase,
        "name": name,
    }
    row: dict = {
        "run_id": run_id,
        "target_id": symbol,
        "kind": kind,
        "identifier": candidate_id or name,
        "smiles": smiles or None,
        "combined_score": score,
        "subscores": subscores,
        "artifact_paths": [],
    }
    if "sequence" in evidence and evidence["sequence"]:
        row["sequence"] = evidence["sequence"]
    supabase_breaker.call(
        lambda: db.table("candidates").insert(row).execute()
    )


def upsert_target(db, *, run_id: str, rank: int, ensembl_id: str, symbol: str,
                  aggregate_score: float, tdl: str, modality_hint: str,
                  seeded: bool, evidence_trail: dict) -> None:
    # Plain insert (the run's targets were cleared first via clear_targets).
    # Avoids ON CONFLICT, which requires a unique(run_id,symbol) constraint that
    # is not guaranteed to be present on the targets table.
    db.table("targets").insert(
        {
            "run_id": run_id,
            "rank": rank,
            "ensembl_id": ensembl_id,
            "symbol": symbol,
            "aggregate_score": aggregate_score,
            "tdl": tdl,
            "modality_primary": modality_hint,
            "evidence_trail": evidence_trail,
        },
    ).execute()
