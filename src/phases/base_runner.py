"""
PhaseGuard — context manager that wraps every phase execution.

Usage in a phase runner:
    with PhaseGuard(db, run_id, phase=1, config=config) as guard:
        guard.check_budget()
        guard.validate_input(phase0_output, required_keys=["go_no_go"])
        # ... phase body ...
        run_state.mark_phase_completed(db, run_id, phase=1, output=output)
        return output

On any unhandled exception inside the block:
  - log.exception is called (captures full traceback)
  - mark_phase_failed is called in DB
  - exception is re-raised
"""
from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

from src.config.run_config import RunConfig
from src.db import run_state

log = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when a phase would exceed the run's hosted-compute budget."""


class PhaseGuard:
    """Context manager for consistent phase lifecycle management."""

    def __init__(
        self,
        db,
        run_id: str,
        phase: int,
        config: Optional[RunConfig] = None,
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._phase = phase
        self._config = config
        self._t_start: float = 0.0

    def __enter__(self) -> "PhaseGuard":
        self._t_start = time.monotonic()
        run_state.mark_phase_running(self._db, self._run_id, self._phase)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        if exc_type is not None:
            wall = round(time.monotonic() - self._t_start, 1)
            log.exception(
                "[Phase %d] run=%s crashed after %.1fs",
                self._phase,
                self._run_id,
                wall,
            )
            try:
                run_state.mark_phase_failed(
                    self._db,
                    self._run_id,
                    self._phase,
                    error=f"{exc_type.__name__}: {exc_val}",
                )
            except Exception:
                log.warning(
                    "[Phase %d] Could not write failed status to DB for run %s",
                    self._phase,
                    self._run_id,
                )
        return False  # always re-raise

    def check_budget(self) -> None:
        """Raise BudgetExceededError if the run has already spent its budget."""
        if self._config is None:
            return
        budget = float(getattr(self._config, "budget_hosted_usd", 0) or 0)
        if budget <= 0:
            return
        try:
            resp = (
                self._db.table("compute_log")
                .select("cost_usd")
                .eq("run_id", self._run_id)
                .execute()
            )
            spent = sum(float(r.get("cost_usd") or 0) for r in (resp.data or []))
            if spent >= budget:
                raise BudgetExceededError(
                    f"Budget ${budget:.2f} exceeded (spent ${spent:.2f}); "
                    f"phase {self._phase} aborted"
                )
            log.info(
                "[Phase %d] Budget check: $%.2f / $%.2f used",
                self._phase,
                spent,
                budget,
            )
        except BudgetExceededError:
            raise
        except Exception as exc:
            log.warning("[Phase %d] Budget check failed (non-fatal): %s", self._phase, exc)

    def validate_input(
        self,
        data: Optional[Dict[str, Any]],
        required_keys: List[str],
        source_phase: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate that a prior phase's output contains all required keys.
        Returns the dict (empty dict if None and no required keys).
        Raises ValueError if any required key is missing.
        """
        actual = data or {}
        if required_keys and not actual:
            src = f"Phase {source_phase}" if source_phase is not None else "prior phase"
            raise ValueError(
                f"Phase {self._phase} received empty input from {src}. "
                "Ensure the prior phase completed successfully before running this phase."
            )
        missing = [k for k in required_keys if k not in actual]
        if missing:
            src = f"Phase {source_phase}" if source_phase is not None else "prior phase"
            raise ValueError(
                f"Phase {self._phase} input from {src} is missing required keys: {missing}. "
                "The prior phase may have failed or produced an incompatible output."
            )
        return actual
