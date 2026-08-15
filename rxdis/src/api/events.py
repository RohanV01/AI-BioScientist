"""
In-process event bus for live run observability.

The pipeline runs in a background *thread* (see orchestrator.py) while the
FastAPI event loop serves WebSocket clients on the main thread. An ``EventHub``
bridges the two: the worker thread calls ``hub.emit(...)`` (thread-safe), which
appends to a replay ring-buffer and fan-outs to every subscribed asyncio.Queue
via ``loop.call_soon_threadsafe``.

The runners are already densely instrumented with ``log.info("[1.3] …")`` style
messages, so we capture *every step* simply by attaching a logging.Handler that
forwards records to the run's hub — no runner changes required. The same handler
sniffs a handful of regexes to surface headline micro-metrics (genes ingested,
embedding dims, AUROC, …) as structured ``metric`` events.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

log = logging.getLogger(__name__)

_BUFFER = 4000           # events retained per run for replay on (re)connect
_MEMINFO = Path("/proc/meminfo")
_LOADAVG = Path("/proc/loadavg")


# ── EventHub ───────────────────────────────────────────────────────────────

class EventHub:
    """Thread-safe pub/sub + replay buffer for one run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._seq = 0
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=_BUFFER)
        self._subs: Set["asyncio.Queue[Dict[str, Any]]"] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.done = False

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, etype: str, **fields: Any) -> Dict[str, Any]:
        """Build, buffer, and fan-out an event. Safe to call from any thread."""
        with self._lock:
            self._seq += 1
            evt = {"seq": self._seq, "ts": time.time(), "type": etype, **fields}
            self._buffer.append(evt)
            subs = list(self._subs)
            loop = self._loop
        for q in subs:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_safe_put, q, evt)
            else:  # same-thread / loop not yet running
                _safe_put(q, evt)
        return evt

    def subscribe(self) -> "asyncio.Queue[Dict[str, Any]]":
        q: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=8000)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[Dict[str, Any]]") -> None:
        with self._lock:
            self._subs.discard(q)

    def replay(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._buffer)


def _safe_put(q: "asyncio.Queue[Dict[str, Any]]", evt: Dict[str, Any]) -> None:
    try:
        q.put_nowait(evt)
    except asyncio.QueueFull:
        pass  # slow consumer — drop rather than block the producer


# ── Registry ─────────────────────────────────────────────────────────────────

class HubRegistry:
    def __init__(self) -> None:
        self._hubs: Dict[str, EventHub] = {}
        self._lock = threading.Lock()

    def get_or_create(self, run_id: str) -> EventHub:
        with self._lock:
            hub = self._hubs.get(run_id)
            if hub is None:
                hub = EventHub(run_id)
                self._hubs[run_id] = hub
            return hub

    def get(self, run_id: str) -> Optional[EventHub]:
        with self._lock:
            return self._hubs.get(run_id)


registry = HubRegistry()


# ── Logging capture ────────────────────────────────────────────────────────

# (compiled regex, extractor -> list[(key, value, label, unit)])
_METRIC_RULES = [
    (re.compile(r"Final matrix:\s*([\d,]+)\s*genes\s*[×x]\s*([\d,]+)\s*features"),
     lambda m: [("genes", _int(m.group(1)), "Rows Ingested", ""),
                ("features", _int(m.group(2)), "Feature Columns", "")]),
    (re.compile(r"Embedding block:\s*\(\s*[\d,]+\s*,\s*([\d,]+)\s*\)"),
     lambda m: [("string_dims", _int(m.group(1)), "STRING Vectors", "dim")]),
    (re.compile(r"Universe:\s*([\d,]+)\s*genes"),
     lambda m: [("universe", _int(m.group(1)), "Gene Universe", "")]),
    (re.compile(r"([\d,]+)\s*positives,\s*([\d,]+)\s*unlabeled,\s*([\d,]+)\s*bags"),
     lambda m: [("positives", _int(m.group(1)), "Positives", ""),
                ("bags", _int(m.group(3)), "PU Bags", "")]),
    (re.compile(r"AUROC\(?(?:LOO)?\)?:\s*([0-9]*\.?[0-9]+)"),
     lambda m: [("auroc", float(m.group(1)), "AUROC (LOO)", "")]),
    (re.compile(r"Complete:\s*([\d,]+)\s*targets"),
     lambda m: [("targets", _int(m.group(1)), "Ranked Targets", "")]),
    (re.compile(r"Validated\s*([\d,]+)\s*targets;\s*([\d,]+)\s*passed"),
     lambda m: [("validated", _int(m.group(1)), "Validated", ""),
                ("passed", _int(m.group(2)), "Passed", "")]),
]


def _int(s: str) -> int:
    return int(s.replace(",", ""))


class HubLogHandler(logging.Handler):
    """Forwards log records produced by *this run's worker thread* to its hub."""

    def __init__(self, hub: EventHub, thread_id: int) -> None:
        super().__init__(level=logging.INFO)
        self.hub = hub
        self.thread_id = thread_id

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self.thread_id:
            return  # isolate concurrent runs — only our worker thread's logs
        try:
            msg = record.getMessage()
        except Exception:
            return
        self.hub.emit(
            "log",
            level=record.levelname,
            logger=record.name,
            message=msg,
        )
        for rx, extract in _METRIC_RULES:
            m = rx.search(msg)
            if m:
                for key, value, label, unit in extract(m):
                    self.hub.emit("metric", key=key, value=value, label=label, unit=unit)


class _AttachedCapture:
    """Context manager: route src.* logs from the current thread into `hub`."""

    def __init__(self, hub: EventHub) -> None:
        self.hub = hub
        self.handler: Optional[HubLogHandler] = None
        self._targets = [logging.getLogger("src"), logging.getLogger("scripts")]

    def __enter__(self) -> "_AttachedCapture":
        self.handler = HubLogHandler(self.hub, threading.get_ident())
        for lg in self._targets:
            lg.addHandler(self.handler)
            if lg.level == logging.NOTSET or lg.level > logging.INFO:
                lg.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.handler is not None:
            for lg in self._targets:
                lg.removeHandler(self.handler)


def capture_to_hub(hub: EventHub) -> _AttachedCapture:
    return _AttachedCapture(hub)


# ── Hardware telemetry (psutil-free; Linux /proc + nvidia-smi) ───────────────

def read_telemetry() -> Dict[str, Any]:
    """RAM (/proc/meminfo) + VRAM (nvidia-smi) + load. Non-blocking, best-effort."""
    out: Dict[str, Any] = {
        "ts": time.time(),
        "ram_used_gb": None, "ram_total_gb": None, "ram_pct": None,
        "vram_used_mb": None, "vram_total_mb": None, "vram_pct": None,
        "cpu_pct": None,
    }
    # RAM
    try:
        info: Dict[str, int] = {}
        for line in _MEMINFO.read_text().splitlines():
            k, _, rest = line.partition(":")
            info[k.strip()] = int(rest.strip().split()[0])  # kB
        total = info.get("MemTotal", 0) / 1024 / 1024
        avail = info.get("MemAvailable", 0) / 1024 / 1024
        used = max(0.0, total - avail)
        out["ram_total_gb"] = round(total, 1)
        out["ram_used_gb"] = round(used, 1)
        out["ram_pct"] = round(100 * used / total, 0) if total else None
    except Exception:
        pass
    # VRAM
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        first = (res.stdout or "").strip().splitlines()
        if first:
            u, t = [int(x.strip()) for x in first[0].split(",")[:2]]
            out["vram_used_mb"] = u
            out["vram_total_mb"] = t
            out["vram_pct"] = round(100 * u / t, 0) if t else None
    except Exception:
        pass
    # CPU (rough): 1-min loadavg normalised by core count.
    try:
        import os
        la1 = float(_LOADAVG.read_text().split()[0])
        ncpu = os.cpu_count() or 1
        out["cpu_pct"] = round(min(100.0, 100 * la1 / ncpu), 0)
    except Exception:
        pass
    return out
