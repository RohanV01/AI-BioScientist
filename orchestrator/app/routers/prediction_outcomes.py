"""Prediction/reality feedback loop endpoints (docs/18-platform-
capability-gaps.md Pass 1 #2). Real DB writes/reads against
`PredictionOutcome` via `app/prediction_tracking.py` -- no external
network call, no new architecture.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.prediction_tracking import (
    InvalidOutcome,
    ToolCallNotFound,
    get_tool_track_record,
    record_prediction_outcome,
)

router = APIRouter()


class RecordOutcomeRequest(BaseModel):
    outcome: str  # validated|contradicted|inconclusive
    recorded_by_user_id: str
    notes: str | None = None


@router.post("/tool-calls/{tool_call_id}/outcome")
async def post_prediction_outcome(
    tool_call_id: uuid.UUID, body: RecordOutcomeRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        record = await record_prediction_outcome(
            db, tool_call_id=tool_call_id, outcome=body.outcome,
            recorded_by_user_id=body.recorded_by_user_id, notes=body.notes,
        )
    except ToolCallNotFound:
        raise HTTPException(status_code=404, detail="No tool call found with that ID.")
    except InvalidOutcome as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "id": str(record.id),
        "tool_call_id": str(record.tool_call_id),
        "outcome": record.outcome,
        "notes": record.notes,
        "recorded_by_user_id": record.recorded_by_user_id,
        "recorded_at": record.recorded_at.isoformat(),
    }


@router.get("/tool-sources/{tool_source_name}/track-record")
async def get_track_record(tool_source_name: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await get_tool_track_record(db, tool_source_name)
    if not result["found"]:
        raise HTTPException(status_code=404, detail="No tool source found with that name.")
    return result
