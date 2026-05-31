"""
Run orchestrator — drives Phase 0 → N inline in a background thread.

Why inline (not Celery): the post-pivot Phase 1 is CPU/RAM-only and the studio is
single-user/local, so running in a daemon thread keeps the moving parts to two
processes (this API + the Vite dev server) and lets the UI watch every step live
through the EventHub. The Celery tasks in src/workers remain for later/scaled use.

Execution depth is capped at Phase 3 (the highest implemented phase). Phases 4–9
are reported to the UI as `not_implemented` so the pipeline tree stays complete.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from src.api.events import EventHub, capture_to_hub, read_telemetry, registry
from src.config.run_config import RunConfig
from src.db.supabase_client import get_service_client

log = logging.getLogger(__name__)

PHASE_NAMES: Dict[int, str] = {
    0: "Setup & Health",
    1: "Target ID",
    2: "Target Validation",
    3: "Modality Selection",
    4: "Repurposing",
    5: "De Novo Small Molecule",
    6: "De Novo Biologic",
    7: "Multi-Parameter Optimization",
    8: "Validation Gate",
    9: "Packaging",
}
MAX_IMPLEMENTED_PHASE = 3

# run_id -> thread, to prevent double-starts
_active: Dict[str, threading.Thread] = {}
_active_lock = threading.Lock()


def is_running(run_id: str) -> bool:
    with _active_lock:
        t = _active.get(run_id)
        return bool(t and t.is_alive())


def start_run(run_id: str, config: RunConfig, hub: EventHub, through_phase: int = 1) -> None:
    """Spawn the worker thread for `run_id`. No-op if already running."""
    with _active_lock:
        if run_id in _active and _active[run_id].is_alive():
            log.warning("[orch] run %s already active", run_id)
            return
        through_phase = max(0, min(through_phase, MAX_IMPLEMENTED_PHASE))
        t = threading.Thread(
            target=_run_worker, args=(run_id, config, hub, through_phase),
            name=f"run-{run_id[:8]}", daemon=True,
        )
        _active[run_id] = t
    t.start()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phase_snapshot(hub: EventHub, through_phase: int, intent_phases: set) -> None:
    """Emit an initial status for every phase so the UI tree renders complete."""
    for p in range(10):
        if p <= through_phase:
            status = "pending"
        elif p > MAX_IMPLEMENTED_PHASE:
            status = "not_implemented"
        elif p in intent_phases:
            status = "skipped"          # implemented & in plan, but beyond chosen depth
        else:
            status = "skipped"          # excluded by intent_mode
        hub.emit("phase", phase=p, name=PHASE_NAMES[p], status=status)


def _run_worker(run_id: str, config: RunConfig, hub: EventHub, through_phase: int) -> None:
    intent_phases = set(config.phases_to_run())
    hub.emit("run", status="running", through_phase=through_phase)
    _phase_snapshot(hub, through_phase, intent_phases)
    hub.emit("telemetry", **read_telemetry())

    db = None
    try:
        db = get_service_client()
        db.table("runs").update(
            {"status": "running", "updated_at": _now()}
        ).eq("id", run_id).execute()
    except Exception as exc:
        hub.emit("log", level="ERROR", logger="orchestrator",
                 message=f"Supabase unavailable: {exc}")
        hub.emit("run", status="failed", error=f"Supabase unavailable: {exc}")
        hub.done = True
        _clear(run_id)
        return

    with capture_to_hub(hub):
        try:
            from src.phases.phase0.runner import run_phase0
            from src.phases.phase1.runner import run_phase1
            from src.phases.phase2.runner import run_phase2
            from src.phases.phase3.runner import run_phase3

            # ── Phase 0 ────────────────────────────────────────────────────────
            hub.emit("phase", phase=0, name=PHASE_NAMES[0], status="running")
            p0 = run_phase0(run_id=run_id, config=config, db=db)
            hub.emit("note", phase=0, title="Health check", data={
                "go_no_go": p0.get("go_no_go"),
                "cost_estimate_usd": p0.get("cost_estimate_usd"),
                "credentials": p0.get("credentials", []),
                "databases": p0.get("databases", []),
                "missing_required": p0.get("missing_required", []),
                "summary": p0.get("summary", ""),
            })
            if p0.get("go_no_go") != "go":
                hub.emit("phase", phase=0, name=PHASE_NAMES[0], status="failed")
                hub.emit("run", status="failed",
                         error="Phase 0 no_go",
                         missing_required=p0.get("missing_required", []))
                _finalize_db(db, run_id, "failed")
                hub.done = True
                _clear(run_id)
                return
            hub.emit("phase", phase=0, name=PHASE_NAMES[0], status="completed")
            hub.emit("telemetry", **read_telemetry())

            # ── Phase 1 ────────────────────────────────────────────────────────
            hub.emit("phase", phase=1, name=PHASE_NAMES[1], status="running")
            p1 = run_phase1(run_id=run_id, config=config, db=db, phase0_output=p0)
            hub.emit("note", phase=1, title="Target identification", data={
                "efo_id": p1.get("efo_id"),
                "disease_label": p1.get("disease_label"),
                "model": p1.get("model", {}),
                "n_targets": len(p1.get("ranked_targets", [])),
                "wall_time_s": p1.get("wall_time_s"),
            })
            hub.emit("phase", phase=1, name=PHASE_NAMES[1], status="completed")
            hub.emit("targets_ready", phase=1)
            hub.emit("telemetry", **read_telemetry())

            p2 = None
            if through_phase >= 2:
                hub.emit("phase", phase=2, name=PHASE_NAMES[2], status="running")
                p2 = run_phase2(run_id=run_id, config=config, db=db, phase1_output=p1)
                hub.emit("note", phase=2, title="Target validation", data={
                    "n_validated": p2.get("n_validated"),
                    "n_passed": p2.get("n_passed"),
                    "threshold_used": p2.get("threshold_used"),
                })
                hub.emit("phase", phase=2, name=PHASE_NAMES[2], status="completed")
                hub.emit("targets_ready", phase=2)
                hub.emit("telemetry", **read_telemetry())

            if through_phase >= 3 and p2 is not None:
                hub.emit("phase", phase=3, name=PHASE_NAMES[3], status="running")
                p3 = run_phase3(run_id=run_id, config=config, db=db, phase2_output=p2)
                hub.emit("note", phase=3, title="Modality selection", data={
                    "branch_summary": p3.get("branch_summary", {}),
                })
                hub.emit("phase", phase=3, name=PHASE_NAMES[3], status="completed")
                hub.emit("targets_ready", phase=3)

            _finalize_db(db, run_id, "completed", current_phase=through_phase)
            hub.emit("telemetry", **read_telemetry())
            hub.emit("run", status="completed", through_phase=through_phase)
            log.info("[orch] run %s completed through phase %d", run_id, through_phase)

        except Exception as exc:  # noqa: BLE001
            log.exception("[orch] run %s failed", run_id)
            hub.emit("log", level="ERROR", logger="orchestrator", message=f"Run failed: {exc}")
            hub.emit("run", status="failed", error=str(exc))
            _finalize_db(db, run_id, "failed")
        finally:
            hub.done = True
            _clear(run_id)


def _finalize_db(db, run_id: str, status: str, current_phase: Optional[int] = None) -> None:
    if db is None:
        return
    patch = {"status": status, "updated_at": _now()}
    if current_phase is not None:
        patch["current_phase"] = current_phase
    try:
        db.table("runs").update(patch).eq("id", run_id).execute()
    except Exception as exc:
        log.warning("[orch] failed to set run status=%s: %s", status, exc)


def _clear(run_id: str) -> None:
    with _active_lock:
        _active.pop(run_id, None)
