"""
Celery task wrappers for Phase 0 and Phase 1.
Each task: loads DB, calls runner, handles exceptions + retries.
"""
from __future__ import annotations
import logging

from celery import Task
from celery.exceptions import Retry

from .celery_app import app
from src.config.run_config import RunConfig
from src.db.supabase_client import get_service_client

log = logging.getLogger(__name__)


class _BasePhaseTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        log.error("Task %s failed: %s", task_id, exc)


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

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        return run_phase0(run_id=run_id, config=config, db=db)
    except Exception as exc:
        log.exception("Phase 0 failed for run %s", run_id)
        try:
            db = get_service_client()
            from src.db.run_state import mark_phase_failed
            mark_phase_failed(db, run_id, phase=0, error=str(exc))
        except Exception:
            pass
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

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        return run_phase1(run_id=run_id, config=config, db=db, phase0_output=phase0_output)
    except Exception as exc:
        log.exception("Phase 1 failed for run %s", run_id)
        try:
            db = get_service_client()
            from src.db.run_state import mark_phase_failed
            mark_phase_failed(db, run_id, phase=1, error=str(exc))
        except Exception:
            pass
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

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        return run_phase2(run_id=run_id, config=config, db=db, phase1_output=phase1_output)
    except Exception as exc:
        log.exception("Phase 2 failed for run %s", run_id)
        try:
            db = get_service_client()
            from src.db.run_state import mark_phase_failed
            mark_phase_failed(db, run_id, phase=2, error=str(exc))
        except Exception:
            pass
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

    try:
        config = RunConfig.model_validate(config_dict)
        db = get_service_client()
        return run_phase3(run_id=run_id, config=config, db=db, phase2_output=phase2_output)
    except Exception as exc:
        log.exception("Phase 3 failed for run %s", run_id)
        try:
            db = get_service_client()
            from src.db.run_state import mark_phase_failed
            mark_phase_failed(db, run_id, phase=3, error=str(exc))
        except Exception:
            pass
        raise self.retry(exc=exc)
