"""Serves the full body of a Response as a plain markdown file
(docs/05-ux-behavior.md Section 3) -- the "link-out to a plain rendered
HTML/markdown file the Orchestrator Service serves locally" for
structured output too large to render inline in a Mattermost
attachment. No canvas view at MVP; this is it.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Response

router = APIRouter()


@router.get("/reports/{response_id}")
async def get_report(response_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    response = await db.get(Response, response_id)
    if response is None:
        raise HTTPException(status_code=404, detail="No response found with that ID.")
    return PlainTextResponse(response.body, media_type="text/markdown")
