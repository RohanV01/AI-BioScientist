"""
Helpers for reading and writing run/phase state to Supabase.
All writes go through the service client (workers).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_phase_running(db, run_id: str, phase: int) -> None:
    db.table("phase_results").upsert(
        {"run_id": run_id, "phase": phase, "status": "running", "started_at": _now()},
        on_conflict="run_id,phase",
    ).execute()
    db.table("runs").update({"current_phase": phase, "status": "running", "updated_at": _now()}).eq("id", run_id).execute()


def mark_phase_completed(db, run_id: str, phase: int, output: dict, artifacts: list[str] | None = None) -> None:
    db.table("phase_results").upsert(
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


def mark_phase_failed(db, run_id: str, phase: int, error: str) -> None:
    db.table("phase_results").upsert(
        {"run_id": run_id, "phase": phase, "status": "failed", "error": error, "finished_at": _now()},
        on_conflict="run_id,phase",
    ).execute()
    db.table("runs").update({"status": "failed", "updated_at": _now()}).eq("id", run_id).execute()


def get_phase_output(db, run_id: str, phase: int) -> Optional[dict]:
    resp = (
        db.table("phase_results")
        .select("output_json")
        .eq("run_id", run_id)
        .eq("phase", phase)
        .eq("status", "completed")
        .single()
        .execute()
    )
    return resp.data["output_json"] if resp.data else None


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


def update_target_routing(db, *, run_id: str, symbol: str,
                          modality_primary: str, modality_secondary: Optional[str]) -> None:
    """Phase 3 — write final modality routing onto an existing target row."""
    db.table("targets").update({
        "modality_primary": modality_primary,
        "modality_secondary": modality_secondary,
    }).eq("run_id", run_id).eq("symbol", symbol).execute()


def clear_targets(db, run_id: str) -> None:
    """Delete all target rows for a run. Phase 1 owns these rows, so it clears
    them once before (re)writing — this makes persistence independent of any
    unique(run_id,symbol) constraint (which may not exist in the DB) and makes
    re-runs idempotent."""
    db.table("targets").delete().eq("run_id", run_id).execute()


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
