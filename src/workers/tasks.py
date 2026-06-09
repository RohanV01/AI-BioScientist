"""
Celery task wrappers for Phase 0 and Phase 1.
Each task: loads DB, calls runner, handles exceptions + retries.
"""
from __future__ import annotations
import logging
import threading

from celery import Task
from celery.exceptions import Retry

from .celery_app import app
from src.config.run_config import RunConfig
from src.db.supabase_client import get_service_client
from src.db.run_state import mark_phase_failed

log = logging.getLogger(__name__)

# Task deduplication: tracks active (run_id, phase) keys
_active_tasks: set = set()
_active_tasks_lock = threading.Lock()


def _is_duplicate(run_id: str, phase: int, task_id: str) -> bool:
    """Return True if a task for this (run_id, phase) is already running."""
    key = f"{run_id}:phase{phase}"
    with _active_tasks_lock:
        if key in _active_tasks:
            log.warning(
                "Duplicate task rejected: run=%s phase=%d task=%s", run_id, phase, task_id
            )
            return True
        _active_tasks.add(key)
    return False


def _fail(run_id: str, phase: int, exc: Exception) -> None:
    key = f"{run_id}:phase{phase}"
    with _active_tasks_lock:
        _active_tasks.discard(key)
    try:
        mark_phase_failed(get_service_client(), run_id, phase=phase, error=str(exc))
    except Exception:
        pass


class _BasePhaseTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        log.error("Task %s failed: %s", task_id, exc)
        # Clean up any deduplication keys by scanning for task_id prefix
        # (we don't know run_id here, so best-effort cleanup)
        with _active_tasks_lock:
            # Nothing to do without run_id context; cleanup happens via _fail
            pass

    def on_success(self, retval, task_id, args, kwargs):
        pass


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase0_task",
    max_retries=2,
    default_retry_delay=30,
    queue="cpu",
)
def run_phase0_task(self, run_id: str, config_dict: dict) -> dict:
    """
    Celery task: run Phase 0 health checks.
    config_dict is the serialised RunConfig.
    """
    from src.phases.phase0.runner import run_phase0

    if _is_duplicate(run_id, 0, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        result = run_phase0(run_id=run_id, config=config, db=db)
        key = f"{run_id}:phase0"
        with _active_tasks_lock:
            _active_tasks.discard(key)
        return result
    except Exception as exc:
        log.exception("Phase 0 failed for run %s", run_id)
        _fail(run_id, 0, exc)
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase1_task",
    max_retries=1,
    default_retry_delay=60,
    queue="llm",
    time_limit=7200,    # 2h hard limit
    soft_time_limit=6900,
)
def run_phase1_task(self, run_id: str, config_dict: dict, phase0_output: dict) -> dict:
    """
    Celery task: run Phase 1 target identification.
    phase0_output is the JSON from Phase 0.
    """
    from src.phases.phase1.runner import run_phase1

    if _is_duplicate(run_id, 1, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        result = run_phase1(run_id=run_id, config=config, db=db, phase0_output=phase0_output)
        key = f"{run_id}:phase1"
        with _active_tasks_lock:
            _active_tasks.discard(key)
        return result
    except Exception as exc:
        log.exception("Phase 1 failed for run %s", run_id)
        _fail(run_id, 1, exc)
        # Phase 1 is long; only retry once
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase2_task",
    max_retries=1,
    default_retry_delay=60,
    queue="hosted",          # structure/NIM/Modal + DB lookups + llm interpretation
    time_limit=10800,        # 3h hard limit (per-target structure fetch can be slow)
    soft_time_limit=10500,
)
def run_phase2_task(self, run_id: str, config_dict: dict, phase1_output: dict) -> dict:
    """Celery task: run Phase 2 target validation."""
    from src.phases.phase2.runner import run_phase2

    if _is_duplicate(run_id, 2, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        result = run_phase2(run_id=run_id, config=config, db=db, phase1_output=phase1_output)
        key = f"{run_id}:phase2"
        with _active_tasks_lock:
            _active_tasks.discard(key)
        return result
    except Exception as exc:
        log.exception("Phase 2 failed for run %s", run_id)
        _fail(run_id, 2, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase3_task",
    max_retries=2,
    default_retry_delay=30,
    queue="llm",             # fast rule engine + grey-zone LLM gate
)
def run_phase3_task(self, run_id: str, config_dict: dict, phase2_output: dict) -> dict:
    """Celery task: run Phase 3 modality selection."""
    from src.phases.phase3.runner import run_phase3

    if _is_duplicate(run_id, 3, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        result = run_phase3(run_id=run_id, config=config, db=db, phase2_output=phase2_output)
        key = f"{run_id}:phase3"
        with _active_tasks_lock:
            _active_tasks.discard(key)
        return result
    except Exception as exc:
        log.exception("Phase 3 failed for run %s", run_id)
        _fail(run_id, 3, exc)
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase4_task",
    max_retries=1,
    default_retry_delay=60,
    queue="hosted",
    time_limit=14400,
    soft_time_limit=14100,
)
def run_phase4_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 4 drug repurposing."""
    from src.phases.phase4.runner import run_phase4
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 4, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p1 = get_phase_output(db, run_id, 1) or {}
        p2 = get_phase_output(db, run_id, 2) or {}
        p3 = get_phase_output(db, run_id, 3) or {}
        result = run_phase4(run_id=run_id, config=config, db=db,
                            phase2_output=p2, phase3_output=p3, phase1_output=p1)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase4")
        return result or {}
    except Exception as exc:
        log.exception("Phase 4 failed for run %s", run_id)
        _fail(run_id, 4, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase5_task",
    max_retries=1,
    default_retry_delay=60,
    queue="llm",
    time_limit=14400,
    soft_time_limit=14100,
)
def run_phase5_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 5 de novo small molecule generation."""
    from src.phases.phase5.runner import run_phase5
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 5, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p1 = get_phase_output(db, run_id, 1) or {}
        p2 = get_phase_output(db, run_id, 2) or {}
        p3 = get_phase_output(db, run_id, 3) or {}
        # Best-effort: if P4 finished before P5 (serial runs or lucky chord ordering)
        p4 = get_phase_output(db, run_id, 4) or {}
        result = run_phase5(run_id=run_id, config=config, db=db,
                            phase2_output=p2, phase3_output=p3, phase1_output=p1,
                            phase4_output=p4 if p4 else None)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase5")
        return result or {}
    except Exception as exc:
        log.exception("Phase 5 failed for run %s", run_id)
        _fail(run_id, 5, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase6_task",
    max_retries=1,
    default_retry_delay=60,
    queue="llm",
    time_limit=14400,
    soft_time_limit=14100,
)
def run_phase6_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 6 biologic design."""
    from src.phases.phase6.runner import run_phase6
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 6, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p1 = get_phase_output(db, run_id, 1) or {}
        p2 = get_phase_output(db, run_id, 2) or {}
        p3 = get_phase_output(db, run_id, 3) or {}
        result = run_phase6(run_id=run_id, config=config, db=db,
                            phase2_output=p2, phase3_output=p3, phase1_output=p1)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase6")
        return result or {}
    except Exception as exc:
        log.exception("Phase 6 failed for run %s", run_id)
        _fail(run_id, 6, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase7_task",
    max_retries=1,
    default_retry_delay=60,
    queue="cpu",
    time_limit=7200,
    soft_time_limit=6900,
)
def run_phase7_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 7 multi-parameter optimization."""
    from src.phases.phase7.runner import run_phase7
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 7, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p2 = get_phase_output(db, run_id, 2) or {}
        p5 = get_phase_output(db, run_id, 5) or {}
        p6 = get_phase_output(db, run_id, 6) or {}
        result = run_phase7(run_id=run_id, config=config, db=db,
                            phase5_output=p5, phase6_output=p6, phase2_output=p2)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase7")
        return result or {}
    except Exception as exc:
        log.exception("Phase 7 failed for run %s", run_id)
        _fail(run_id, 7, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase8_task",
    max_retries=1,
    default_retry_delay=60,
    queue="hosted",
    time_limit=7200,
    soft_time_limit=6900,
)
def run_phase8_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 8 validation gate."""
    from src.phases.phase8.runner import run_phase8
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 8, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p2 = get_phase_output(db, run_id, 2) or {}
        p4 = get_phase_output(db, run_id, 4) or {}
        p7 = get_phase_output(db, run_id, 7) or {}
        result = run_phase8(run_id=run_id, config=config, db=db,
                            phase7_output=p7, phase4_output=p4, phase2_output=p2)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase8")
        return result or {}
    except Exception as exc:
        log.exception("Phase 8 failed for run %s", run_id)
        _fail(run_id, 8, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@app.task(
    bind=True,
    base=_BasePhaseTask,
    name="src.workers.tasks.run_phase9_task",
    max_retries=1,
    default_retry_delay=30,
    queue="cpu",
    time_limit=3600,
    soft_time_limit=3300,
)
def run_phase9_task(self, run_id: str, config_dict: dict) -> dict:
    """Celery task: run Phase 9 packaging and reporting."""
    from src.phases.phase9.runner import run_phase9
    from src.db.run_state import get_phase_output

    if _is_duplicate(run_id, 9, self.request.id):
        return {}

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        p1 = get_phase_output(db, run_id, 1) or {}
        p2 = get_phase_output(db, run_id, 2) or {}
        p3 = get_phase_output(db, run_id, 3) or {}
        result = run_phase9(run_id=run_id, config=config, db=db,
                            phase1_output=p1, phase2_output=p2, phase3_output=p3)
        with _active_tasks_lock:
            _active_tasks.discard(f"{run_id}:phase9")
        return result or {}
    except Exception as exc:
        log.exception("Phase 9 failed for run %s", run_id)
        _fail(run_id, 9, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
