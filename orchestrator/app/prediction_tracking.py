"""Prediction/reality feedback loop (docs/18-platform-capability-gaps.md
Pass 1 #2): the platform can compute a docking affinity, a solubility
prediction, an FBA growth rate -- but had no mechanism to later record
"this prediction was validated/contradicted by an actual result."
Without that loop the system can never get calibrated against ground
truth. Real DB writes/reads against `PredictionOutcome`, no external
network call, same shape as `app/methods_report.py`.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PredictionOutcome, ToolCall, ToolSource

VALID_OUTCOMES = {"validated", "contradicted", "inconclusive"}


class ToolCallNotFound(ValueError):
    pass


class InvalidOutcome(ValueError):
    pass


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def record_prediction_outcome(
    db: AsyncSession,
    *,
    tool_call_id: uuid.UUID,
    outcome: str,
    recorded_by_user_id: str,
    notes: str | None = None,
) -> PredictionOutcome:
    """Record a real-world outcome (validated/contradicted/inconclusive)
    against a specific prior ToolCall -- e.g. "this docking prediction
    was later confirmed/refuted by a wet-lab assay." Never inferred or
    guessed here: the caller (a researcher, via a Mattermost command or
    the API directly) is asserting a real-world fact this platform has
    no way to independently verify -- that assertion, and who made it,
    is exactly what gets recorded."""
    if outcome not in VALID_OUTCOMES:
        raise InvalidOutcome(f"outcome must be one of {sorted(VALID_OUTCOMES)}, got {outcome!r}")
    tool_call = await db.get(ToolCall, tool_call_id)
    if tool_call is None:
        raise ToolCallNotFound(f"No tool call found with id {tool_call_id}")

    record = PredictionOutcome(
        tool_call_id=tool_call_id, outcome=outcome, notes=notes, recorded_by_user_id=recorded_by_user_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_tool_track_record(db: AsyncSession, tool_source_name: str) -> dict[str, Any]:
    """Real aggregate calibration stats for one tool source: how many
    of its predictions have actually been checked against reality, and
    how they held up. Answers docs/18's own framing directly: "how
    often has this tool's prediction actually held up." An empty/zero
    result means genuinely no feedback has been recorded yet -- never
    fabricated as a track record that doesn't exist."""
    tool_source = (await db.execute(select(ToolSource).where(ToolSource.name == tool_source_name))).scalars().first()
    if tool_source is None:
        return {"tool_source": tool_source_name, "found": False}

    stmt = (
        select(PredictionOutcome.outcome, func.count())
        .join(ToolCall, PredictionOutcome.tool_call_id == ToolCall.id)
        .where(ToolCall.tool_source_id == tool_source.id)
        .group_by(PredictionOutcome.outcome)
    )
    rows = (await db.execute(stmt)).all()
    counts = {outcome: count for outcome, count in rows}
    total = sum(counts.values())

    return {
        "tool_source": tool_source_name,
        "found": True,
        "total_outcomes_recorded": total,
        "validated": counts.get("validated", 0),
        "contradicted": counts.get("contradicted", 0),
        "inconclusive": counts.get("inconclusive", 0),
        "validation_rate": round(counts.get("validated", 0) / total, 3) if total else None,
    }
