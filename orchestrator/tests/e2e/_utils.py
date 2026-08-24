"""Shared recorder for E2E combo tests (orchestrator/tests/e2e/).

Each combo test chains several tools' .handler() calls directly (same
no-mocking style as the per-tool tests in orchestrator/tests/), and uses
an E2ERecorder to save every step's raw output plus a final verdict to
orchestrator/tests/e2e/results/<combo-name>/<timestamp>/ -- so a human can
review exactly what a run produced without re-running it. That directory
is gitignored; only the code that produces it is committed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_ROOT = Path(__file__).parent / "results"


class FakeAsyncSession:
    """Minimal stand-in for AsyncSession, just enough to exercise
    grounding.create_response()'s real validation logic (the actual
    release-blocking rule, per its own docstring) without a live
    Postgres/docker-compose stack -- add() records pending objects,
    flush() assigns each a fake id the same way a real flush would. Any
    GroundingViolation raised happens before add()/flush() are ever
    called for the invalid-input case, so this never masks the rule
    itself -- it only stands in for real persistence on the valid path."""

    def __init__(self):
        self._pending: list = []

    def add(self, obj):
        self._pending.append(obj)

    async def flush(self):
        import uuid

        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
        self._pending.clear()


def text_of(result: dict[str, Any]) -> str:
    return "\n".join(
        block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
    )


@dataclass
class E2EStep:
    tool: str
    args: dict[str, Any]
    result_text: str


@dataclass
class E2ERecorder:
    combo_name: str
    steps: list[E2EStep] = field(default_factory=list)
    assertions: list[tuple[str, bool, str]] = field(default_factory=list)  # (label, passed, detail)

    async def call(self, label: str, handler, args: dict[str, Any]) -> str:
        """Await a tool's .handler(args) call, record it, return its text."""
        result = await handler(args)
        text = text_of(result)
        self.steps.append(E2EStep(tool=label, args=args, result_text=text))
        return text

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.assertions.append((label, passed, detail))

    def save(self) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = RESULTS_ROOT / self.combo_name / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        raw = [{"tool": s.tool, "args": s.args, "result_text": s.result_text} for s in self.steps]
        (out_dir / "raw.json").write_text(json.dumps(raw, indent=2))

        lines = [f"# E2E: {self.combo_name}", "", f"Run at {ts}", "", "## Chain"]
        for i, s in enumerate(self.steps, 1):
            lines.append(f"### Step {i}: {s.tool}")
            lines.append(f"Args: `{s.args}`")
            lines.append("")
            snippet = s.result_text[:2000] + ("... [truncated]" if len(s.result_text) > 2000 else "")
            lines.append(snippet)
            lines.append("")
        lines.append("## Verdicts")
        for label, passed, detail in self.assertions:
            mark = "PASS" if passed else "FAIL"
            lines.append(f"- [{mark}] {label}" + (f" -- {detail}" if detail else ""))
        (out_dir / "summary.md").write_text("\n".join(lines))

        return out_dir

    def assert_all_passed(self) -> None:
        failed = [(label, detail) for label, passed, detail in self.assertions if not passed]
        out_dir = self.save()
        if failed:
            detail_str = "; ".join(f"{label} ({detail})" for label, detail in failed)
            raise AssertionError(
                f"{self.combo_name}: {len(failed)} hand-off check(s) failed: {detail_str} (see {out_dir})"
            )
