"""
Run orchestrator — drives Phase 0 → N for E2E runs.

Execution strategy (selected at startup):
  1. Celery chain  — preferred when Redis is reachable.
     P0 → P1 → P2 → P3 → chord(P4 | P5 | P6) → P7 → P8 → P9
     P4/P5/P6 run in parallel (chord), then merge into P7.
  2. Thread fallback — used when Redis is unavailable (dev / no-Redis env).
     Same phases, sequential, inline in a daemon thread.

Both paths emit events to the EventHub so the UI stream works identically.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from src.api.events import EventHub, capture_to_hub, read_telemetry, registry
from src.config import settings as _settings
from src.config.run_config import RunConfig
from src.db.run_state import get_phase_output, mark_phase_failed
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
    8: "Packaging",
}
MAX_IMPLEMENTED_PHASE = 8

_active: Dict[str, threading.Thread] = {}
_active_lock = threading.Lock()

# Concurrency cap: reject new thread-path runs when the pool is full
_MAX_THREAD_RUNS: int = _settings.MAX_CONCURRENT_THREAD_RUNS
_thread_semaphore = threading.Semaphore(_MAX_THREAD_RUNS)

def _probe_redis() -> bool:
    """Return True only when Redis is reachable AND at least one Celery worker is live."""
    try:
        from src.config import settings
        import redis as _redis_lib
        r = _redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
    except Exception as exc:
        log.warning("[orch] Redis unavailable (%s) — falling back to thread executor", exc)
        return False

    # Check for live workers via Celery inspect
    try:
        from src.workers.celery_app import celery_app
        inspector = celery_app.control.inspect(timeout=1.5)
        active = inspector.ping()
        if active:
            log.info("[orch] Redis + Celery workers reachable — using Celery chain")
            return True
        log.warning("[orch] Redis reachable but no Celery workers found — falling back to thread executor")
        return False
    except Exception as exc:
        log.warning("[orch] Celery worker probe failed (%s) — falling back to thread executor", exc)
        return False


def is_running(run_id: str) -> bool:
    with _active_lock:
        t = _active.get(run_id)
        return bool(t and t.is_alive())


def start_run(run_id: str, config: RunConfig, hub: EventHub, through_phase: int = 1) -> None:
    """Start an E2E run. Uses Celery when Redis is available, threads otherwise."""
    through_phase = max(0, min(through_phase, MAX_IMPLEMENTED_PHASE))

    if _probe_redis():
        try:
            _start_celery(run_id, config, hub, through_phase)
        except (ImportError, Exception) as exc:
            log.warning("[orch] Celery dispatch failed (%s) — falling back to thread executor", exc)
            _start_thread(run_id, config, hub, through_phase)
    else:
        _start_thread(run_id, config, hub, through_phase)


# ── Celery path ───────────────────────────────────────────────────────────────

def _start_celery(run_id: str, config: RunConfig, hub: EventHub, through_phase: int) -> None:
    """Dispatch the Celery task chain and launch a lightweight monitor thread
    that polls Celery task state and emits EventHub events for the UI."""
    from celery import chain, chord
    from src.workers.tasks import (
        run_phase0_task, run_phase1_task, run_phase2_task, run_phase3_task,
        run_phase4_task, run_phase5_task, run_phase6_task,
        run_phase7_task, run_phase8_task, run_phase9_task,
    )

    cfg_dict = config.model_dump(mode="json")
    intent_phases = set(config.phases_to_run())

    hub.emit("run", status="running", through_phase=through_phase, executor="celery")
    _phase_snapshot(hub, through_phase, intent_phases)
    hub.emit("telemetry", **read_telemetry())

    # Build the chain up to through_phase
    tasks = [
        run_phase0_task.si(run_id, cfg_dict),
        run_phase1_task.si(run_id, cfg_dict),
    ]
    if through_phase >= 2:
        tasks.append(run_phase2_task.si(run_id, cfg_dict))
    if through_phase >= 3:
        tasks.append(run_phase3_task.si(run_id, cfg_dict))

    # P4/P5/P6 run in parallel via chord, then feed P7
    if through_phase >= 7:
        parallel = []
        if config.de_novo_enabled or through_phase >= 4:
            parallel.append(run_phase4_task.si(run_id, cfg_dict))
        if config.de_novo_enabled:
            parallel.append(run_phase5_task.si(run_id, cfg_dict))
            parallel.append(run_phase6_task.si(run_id, cfg_dict))
        if parallel:
            tasks.append(chord(parallel, run_phase7_task.si(run_id, cfg_dict)))
        else:
            tasks.append(run_phase7_task.si(run_id, cfg_dict))
    elif through_phase in (4, 5, 6):
        # Single branch without chord
        if through_phase >= 4:
            tasks.append(run_phase4_task.si(run_id, cfg_dict))
        if through_phase >= 5 and config.de_novo_enabled:
            tasks.append(run_phase5_task.si(run_id, cfg_dict))
        if through_phase >= 6 and config.de_novo_enabled:
            tasks.append(run_phase6_task.si(run_id, cfg_dict))

    if through_phase >= 8:
        tasks.append(run_phase8_task.si(run_id, cfg_dict))   # Vina validation (silent)
        tasks.append(run_phase9_task.si(run_id, cfg_dict))   # Packaging → P8

    workflow = chain(*tasks)
    async_result = workflow.apply_async()

    # Monitor thread: polls the chain result and emits phase events
    t = threading.Thread(
        target=_celery_monitor,
        args=(run_id, async_result, hub, through_phase, config),
        name=f"mon-{run_id[:8]}",
        daemon=True,
    )
    with _active_lock:
        _active[run_id] = t
    t.start()


def _celery_monitor(run_id: str, async_result, hub: EventHub,
                    through_phase: int, config: RunConfig) -> None:
    """Poll Celery result status every 5 s, emit phase events from DB state."""
    db = get_service_client()
    emitted: set[int] = set()
    poll_interval = 5

    try:
        while not async_result.ready():
            _emit_completed_phases(db, run_id, hub, through_phase, emitted)
            hub.emit("telemetry", **read_telemetry())
            time.sleep(poll_interval)

        # Final sweep
        _emit_completed_phases(db, run_id, hub, through_phase, emitted)
        hub.emit("telemetry", **read_telemetry())

        if async_result.successful():
            hub.emit("run", status="completed", through_phase=through_phase)
            log.info("[orch] Celery run %s completed through phase %d", run_id, through_phase)
        else:
            err = str(async_result.result) if async_result.result else "unknown"
            hub.emit("run", status="failed", error=err)
            log.error("[orch] Celery run %s failed: %s", run_id, err)

    except Exception as exc:
        log.exception("[orch] Monitor thread for %s crashed", run_id)
        hub.emit("run", status="failed", error=str(exc))
    finally:
        hub.done = True
        _clear(run_id)


def _emit_completed_phases(db, run_id: str, hub: EventHub,
                            through_phase: int, emitted: set) -> None:
    """Check DB for newly completed/failed phases and emit events once per phase."""
    try:
        rows = (
            db.table("phase_results")
            .select("phase,status,error")
            .eq("run_id", run_id)
            .execute().data or []
        )
    except Exception:
        return

    for row in rows:
        p = row["phase"]
        status = row["status"]
        if p in emitted:
            continue
        if status in ("completed", "failed"):
            hub.emit(
                "phase", phase=p, name=PHASE_NAMES.get(p, f"Phase {p}"),
                status=status, **({"error": row["error"]} if row.get("error") else {}),
            )
            emitted.add(p)
        elif status == "running" and p not in emitted:
            hub.emit("phase", phase=p, name=PHASE_NAMES.get(p, f"Phase {p}"), status="running")


# ── Thread fallback path ──────────────────────────────────────────────────────

def _start_thread(run_id: str, config: RunConfig, hub: EventHub, through_phase: int) -> None:
    if not _thread_semaphore.acquire(blocking=False):
        log.warning(
            "[orch] Max concurrent thread runs (%d) reached; rejecting run %s",
            _MAX_THREAD_RUNS, run_id,
        )
        hub.emit("run", status="failed",
                 error=f"Server busy: max {_MAX_THREAD_RUNS} concurrent runs. Try again shortly.")
        hub.done = True
        return

    with _active_lock:
        if run_id in _active and _active[run_id].is_alive():
            _thread_semaphore.release()
            log.warning("[orch] run %s already active", run_id)
            return
        t = threading.Thread(
            target=_thread_worker_with_semaphore,
            args=(run_id, config, hub, through_phase),
            name=f"run-{run_id[:8]}",
            daemon=True,
        )
        _active[run_id] = t
    t.start()


def _thread_worker_with_semaphore(run_id: str, config: RunConfig, hub: EventHub, through_phase: int) -> None:
    try:
        _thread_worker(run_id, config, hub, through_phase)
    finally:
        _thread_semaphore.release()


def _run_phase_safely(phase_num: int, fn, **kwargs):
    """Call phase runner fn(**kwargs). If it raises, ensure mark_phase_failed is called."""
    _db = kwargs.get("db")
    _run_id = kwargs.get("run_id", "")
    try:
        return fn(**kwargs)
    except Exception as exc:
        log.exception("[orch] Phase %d failed for run %s", phase_num, _run_id)
        try:
            if _db and _run_id:
                mark_phase_failed(_db, _run_id, phase=phase_num, error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phase_snapshot(hub: EventHub, through_phase: int, intent_phases: set) -> None:
    for p in range(9):
        if p <= through_phase:
            status = "pending"
        elif p > MAX_IMPLEMENTED_PHASE:
            status = "not_implemented"
        else:
            status = "skipped"
        hub.emit("phase", phase=p, name=PHASE_NAMES[p], status=status)


def _thread_worker(run_id: str, config: RunConfig, hub: EventHub, through_phase: int) -> None:
    intent_phases = set(config.phases_to_run())
    hub.emit("run", status="running", through_phase=through_phase, executor="thread")
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

            hub.emit("phase", phase=0, name=PHASE_NAMES[0], status="running")
            p0 = _run_phase_safely(0, run_phase0,
                                   run_id=run_id, config=config, db=db)
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
                hub.emit("run", status="failed", error="Phase 0 no_go",
                         missing_required=p0.get("missing_required", []))
                _finalize_db(db, run_id, "failed")
                hub.done = True
                _clear(run_id)
                return
            hub.emit("phase", phase=0, name=PHASE_NAMES[0], status="completed")
            hub.emit("telemetry", **read_telemetry())

            hub.emit("phase", phase=1, name=PHASE_NAMES[1], status="running")
            p1 = _run_phase_safely(1, run_phase1,
                                   run_id=run_id, config=config, db=db, phase0_output=p0)
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
                from src.phases.phase2.runner import run_phase2
                hub.emit("phase", phase=2, name=PHASE_NAMES[2], status="running")
                p2 = _run_phase_safely(2, run_phase2,
                                       run_id=run_id, config=config, db=db, phase1_output=p1)
                hub.emit("note", phase=2, title="Target validation", data={
                    "n_total": p2.get("n_total"),
                    "n_passing": p2.get("n_passing"),
                    "threshold_used": p2.get("threshold_used"),
                    "wall_time_s": p2.get("wall_time_s"),
                })
                hub.emit("phase", phase=2, name=PHASE_NAMES[2], status="completed")
                hub.emit("telemetry", **read_telemetry())

            p3 = None
            if through_phase >= 3 and p2 is not None:
                from src.phases.phase3.runner import run_phase3
                hub.emit("phase", phase=3, name=PHASE_NAMES[3], status="running")
                p3 = _run_phase_safely(3, run_phase3,
                                       run_id=run_id, config=config, db=db, phase2_output=p2)
                hub.emit("note", phase=3, title="Modality routing", data={
                    "n_routed": len(p3.get("routing", [])),
                    "intent_mode": p3.get("intent_mode"),
                    "wall_time_s": p3.get("wall_time_s"),
                })
                hub.emit("phase", phase=3, name=PHASE_NAMES[3], status="completed")
                hub.emit("telemetry", **read_telemetry())

            p4 = None
            if through_phase >= 4 and p2 is not None and p3 is not None:
                from src.phases.phase4.runner import run_phase4
                hub.emit("phase", phase=4, name=PHASE_NAMES[4], status="running")
                p4 = _run_phase_safely(4, run_phase4,
                                       run_id=run_id, config=config, db=db,
                                       phase2_output=p2, phase3_output=p3, phase1_output=p1)
                hub.emit("note", phase=4, title="Drug repurposing", data={
                    "n_targets_screened": p4.get("n_targets_screened"),
                    "n_candidates_total": p4.get("n_candidates_total"),
                    "wall_time_s": p4.get("wall_time_s"),
                })
                hub.emit("phase", phase=4, name=PHASE_NAMES[4], status="completed")
                hub.emit("telemetry", **read_telemetry())

            p5 = None
            if through_phase >= 5 and p2 is not None and p3 is not None and config.de_novo_enabled:
                from src.phases.phase5.runner import run_phase5
                hub.emit("phase", phase=5, name=PHASE_NAMES[5], status="running")
                p5 = _run_phase_safely(5, run_phase5,
                                       run_id=run_id, config=config, db=db,
                                       phase2_output=p2, phase3_output=p3, phase1_output=p1,
                                       phase4_output=p4)
                hub.emit("note", phase=5, title="De novo SM design", data={
                    "n_targets": p5.get("n_targets"),
                    "n_candidates_total": p5.get("n_candidates_total"),
                    "wall_time_s": p5.get("wall_time_s"),
                })
                hub.emit("phase", phase=5, name=PHASE_NAMES[5], status="completed")
                hub.emit("telemetry", **read_telemetry())

            p6 = None
            if through_phase >= 6 and p2 is not None and p3 is not None and config.de_novo_enabled:
                from src.phases.phase6.runner import run_phase6
                hub.emit("phase", phase=6, name=PHASE_NAMES[6], status="running")
                p6 = _run_phase_safely(6, run_phase6,
                                       run_id=run_id, config=config, db=db,
                                       phase2_output=p2, phase3_output=p3, phase1_output=p1)
                hub.emit("note", phase=6, title="De novo biologic design", data={
                    "n_targets": p6.get("n_targets"),
                    "n_candidates_total": p6.get("n_candidates_total"),
                    "wall_time_s": p6.get("wall_time_s"),
                })
                hub.emit("phase", phase=6, name=PHASE_NAMES[6], status="completed")
                hub.emit("telemetry", **read_telemetry())

            p7 = None
            if through_phase >= 7 and (p5 is not None or p6 is not None):
                from src.phases.phase7.runner import run_phase7
                hub.emit("phase", phase=7, name=PHASE_NAMES[7], status="running")
                p7 = _run_phase_safely(7, run_phase7,
                                       run_id=run_id, config=config, db=db,
                                       phase5_output=p5, phase6_output=p6,
                                       phase2_output=p2, phase3_output=p3)
                hub.emit("note", phase=7, title="MPO optimisation", data={
                    "n_targets": p7.get("n_targets"),
                    "n_pareto_total": p7.get("n_pareto_total"),
                    "wall_time_s": p7.get("wall_time_s"),
                })
                hub.emit("phase", phase=7, name=PHASE_NAMES[7], status="completed")
                hub.emit("telemetry", **read_telemetry())

            # Vina validation runs silently (no hub events) before packaging
            p8 = None
            if through_phase >= 8 and p2 is not None:
                from src.phases.phase8.runner import run_phase8
                p8 = _run_phase_safely(8, run_phase8,
                                       run_id=run_id, config=config, db=db,
                                       phase7_output=p7, phase4_output=p4,
                                       phase2_output=p2, phase3_output=p3)

            if through_phase >= 8:
                from src.phases.phase9.runner import run_phase9
                hub.emit("phase", phase=8, name=PHASE_NAMES[8], status="running")
                p9 = _run_phase_safely(9, run_phase9,
                                       run_id=run_id, config=config, db=db,
                                       phase1_output=p1, phase2_output=p2, phase3_output=p3,
                                       phase4_output=p4, phase5_output=p5, phase6_output=p6,
                                       phase7_output=p7, phase8_output=p8)
                hub.emit("note", phase=8, title="Packaging", data={
                    "package_path": p9.get("package_path"),
                    "package_url": p9.get("package_url"),
                    "candidates_total": p9.get("candidates_total"),
                    "cost_actual_usd": p9.get("cost_actual_usd"),
                    "audit_passed": p9.get("audit", {}).get("audit_passed"),
                    "wall_time_s": p9.get("wall_time_s"),
                })
                hub.emit("phase", phase=8, name=PHASE_NAMES[8], status="completed")
                hub.emit("telemetry", **read_telemetry())
            else:
                _finalize_db(db, run_id, "completed", current_phase=through_phase)

            hub.emit("telemetry", **read_telemetry())
            hub.emit("run", status="completed", through_phase=through_phase)
            log.info("[orch] Thread run %s completed through phase %d", run_id, through_phase)

        except Exception as exc:
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
