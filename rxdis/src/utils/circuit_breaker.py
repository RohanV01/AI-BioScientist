"""
Simple in-process circuit breaker for protecting external service calls (Supabase, Redis).

States: CLOSED → OPEN (on threshold failures) → HALF_OPEN (after recovery timeout) → CLOSED
"""
from __future__ import annotations

import logging
import threading
import time
from functools import wraps
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    log.info("[circuit:%s] HALF_OPEN — testing recovery", self.name)
            return self._state

    def record_success(self) -> None:
        with self._lock:
            if self._state != self.CLOSED:
                log.info("[circuit:%s] recovery confirmed — CLOSED", self.name)
            self._failure_count = 0
            self._state = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                if self._state == self.CLOSED:
                    log.warning(
                        "[circuit:%s] %d failures — OPEN (retry in %.0fs)",
                        self.name,
                        self._failure_count,
                        self.recovery_timeout,
                    )
                self._state = self.OPEN

    def call(self, fn: F, *args, **kwargs):
        """Execute fn, recording success/failure. Raises CircuitOpenError if open."""
        if self.state == self.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is OPEN — refusing DB call. "
                "Will retry after recovery timeout."
            )
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            self.record_failure()
            raise

    def __call__(self, fn: F) -> F:
        """Decorator form."""
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return self.call(fn, *args, **kwargs)
        return wrapper  # type: ignore[return-value]


# Singleton circuit breakers
supabase_breaker = CircuitBreaker("supabase", failure_threshold=5, recovery_timeout=60.0)
redis_breaker = CircuitBreaker("redis", failure_threshold=3, recovery_timeout=30.0)
