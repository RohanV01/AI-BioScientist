"""Receives Mattermost's Outgoing Webhook calls (docs/04-information-
architecture.md: "@mention in any channel... delegates a task"). This is
the Message Router half of docs/07-system-architecture.md's Orchestrator
Service.

Phase 0 scope (docs/10-build-plan.md): create a Task row and post a stub
response -- proves the wiring end-to-end. Routing to a real Agent's
Claude Code/Codex Runner is Phase 1 (the Literature Agent).
"""
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.grounding import create_response
from app.mattermost_client import MattermostClient
from app.models import Agent, Task

router = APIRouter()


@router.post("/webhooks/mattermost")
async def mattermost_outgoing_webhook(
    db: AsyncSession = Depends(get_db),
    token: str = Form(...),
    channel_id: str = Form(...),
    user_id: str = Form(...),
    user_name: str = Form(...),
    post_id: str = Form(...),
    text: str = Form(...),
    trigger_word: str = Form(""),
):
    if settings.mattermost_webhook_secret and token != settings.mattermost_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid webhook token")

    # Phase 0: route everything to whichever agent's bot was actually
    # mentioned isn't wired yet (no real agents exist until Phase 1) --
    # find *any* active agent as a stand-in so the Task/Response plumbing
    # is provably correct end-to-end before real routing logic exists.
    result = await db.execute(select(Agent).where(Agent.active.is_(True)).limit(1))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail="No active agent registered yet -- run the Phase 0 seed script.",
        )

    task = Task(
        org_id=agent.org_id,
        agent_id=agent.id,
        mattermost_thread_id=post_id,
        requested_by_user_id=user_id,
        status="completed",
        raw_request=text,
    )
    db.add(task)
    await db.flush()

    stub_body = (
        f"(stub) Received: {text!r} from @{user_name}. "
        f"Real agent logic isn't wired yet -- this proves the Mattermost -> "
        f"Orchestrator -> Mattermost loop works end-to-end (Phase 0 exit criterion)."
    )
    response = await create_response(
        db,
        task_id=task.id,
        body=stub_body,
        provenance_type="synthesis",  # not grounded -- it's a stub, and says so
    )
    await db.commit()

    # Outgoing Webhooks support a synchronous response body OR an async
    # post via the REST API. We use the synchronous path here since it's
    # simpler and sufficient for the Phase 0 stub -- real agents (Phase 1+)
    # will need the async REST path for progress updates on long-running
    # tasks (docs/05-ux-behavior.md Section 1, FR-7), which is why
    # MattermostClient exists as a separate reusable module already.
    return {"text": stub_body, "response_type": "in_channel"}
