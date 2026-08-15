"""Receives Mattermost's Outgoing Webhook calls (docs/04-information-
architecture.md: "@mention in any channel... delegates a task"). This is
the Message Router half of docs/07-system-architecture.md's Orchestrator
Service.

Phase 1: routes to the real Literature Agent (Claude + PubMed). The
synchronous webhook response is just a receipt (docs/05-ux-behavior.md
Section 1's "immediately react to confirm receipt" rule) -- the actual
agent call runs in the background and posts its real answer via the
Mattermost REST API once done, since a real Claude+tool-use turn takes
longer than Mattermost's synchronous webhook timeout tolerates.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude_runner import run_literature_agent
from app.config import settings
from app.db import async_session, get_db
from app.grounding import Citation, create_response
from app.mattermost_client import MattermostClient
from app.models import Agent, Task, ToolCall
from app.tool_sources import get_or_create_pubmed_tool_source
from app.vault import decrypt

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_agent_and_respond(task_id, agent_id: str, channel_id: str, user_message: str) -> None:
    """Runs in the background, after the webhook has already returned a
    receipt to Mattermost. Owns its own DB session -- the request-scoped
    one from the original call is closed by the time this runs."""
    async with async_session() as db:
        agent = await db.get(Agent, agent_id)
        task = await db.get(Task, task_id)
        if agent is None or not agent.encrypted_mattermost_bot_token:
            logger.error("Agent %s has no bot token configured; cannot post response.", agent_id)
            if task is not None:
                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
            return

        bot_token = decrypt(agent.encrypted_mattermost_bot_token)
        mm = MattermostClient(bot_token)
        try:
            try:
                result = await run_literature_agent(user_message)
            except Exception:
                logger.exception("Literature agent run failed for task %s", task_id)
                await mm.post_message(
                    channel_id,
                    "Something went wrong answering this -- no response was produced. "
                    "This has been logged for review.",
                )
                await create_response(
                    db, task_id=task_id, body="(error: agent run raised an exception)",
                    provenance_type="ungroundable",
                )
                if task is not None:
                    task.status = "failed"
                    task.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            # Persist every real tool call the runner made as a ToolCall row
            # (docs/06-data-model.md) -- this is what lets GroundingLink
            # point at something real instead of a citation string floating
            # free of any actual invocation.
            pubmed_source = await get_or_create_pubmed_tool_source(db)
            tool_call_rows: list[ToolCall] = []
            for tc in result.tool_calls:
                row = ToolCall(
                    task_id=task_id,
                    tool_source_id=pubmed_source.id,
                    request_payload=tc.request,
                    response_payload={"text": tc.result_text},
                    status="ok",
                )
                db.add(row)
                tool_call_rows.append(row)
            if tool_call_rows:
                await db.flush()  # assigns .id to each row before citations reference them

            citations = [
                Citation(
                    tool_call_id=tool_call_rows[c.tool_call_index].id,
                    citation_label=c.label,
                    record_ref=c.pmid,
                )
                for c in result.citations
            ]

            response = await create_response(
                db,
                task_id=task_id,
                body=result.body,
                provenance_type=result.provenance_type,
                citations=citations or None,
            )
            posted = await mm.post_message(channel_id, result.body)
            response.mattermost_message_id = posted.get("id")
            if task is not None:
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
            await db.commit()
        finally:
            await mm.aclose()


@router.post("/webhooks/mattermost")
async def mattermost_outgoing_webhook(
    background_tasks: BackgroundTasks,
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

    # Phase 1: still routes to "any active agent" rather than parsing
    # trigger_word to pick a specific one -- real multi-agent routing is a
    # Phase 4 concern (more than one agent exists then). Fine for now since
    # there's exactly one real agent.
    result = await db.execute(select(Agent).where(Agent.active.is_(True)).limit(1))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail="No active agent registered yet -- run scripts/seed_dev_data.py.",
        )

    task = Task(
        org_id=agent.org_id,
        agent_id=agent.id,
        mattermost_thread_id=post_id,
        requested_by_user_id=user_id,
        status="running",
        raw_request=text,
    )
    db.add(task)
    await db.commit()

    background_tasks.add_task(_run_agent_and_respond, task.id, str(agent.id), channel_id, text)

    # Synchronous receipt only (docs/05-ux-behavior.md Section 1) -- the
    # real answer is posted asynchronously once the agent finishes.
    return {"text": f"🔎 Looking into this, @{user_name} -- one moment...", "response_type": "in_channel"}
