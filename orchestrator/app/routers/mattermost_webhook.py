"""Receives Mattermost's Outgoing Webhook calls -- the one master agent's
entry point (docs/04-information-architecture.md: one bot, any channel/DM,
no per-domain routing to figure out). This is the Message Router half of
docs/07-system-architecture.md's Orchestrator Service.

The synchronous webhook response is just a receipt (docs/05-ux-behavior.md
Section 1's "immediately react to confirm receipt" rule) -- the actual
agent run (Plan -> Execute -> Synthesize) happens in the background and
posts to the channel as it goes: the stated methodology as soon as it's
produced, then the final synthesized report once execution finishes.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude_runner import run_agent
from app.config import settings
from app.db import async_session, get_db
from app.experiment_context import current_experiment_dir
from app.grounding import Citation, create_response
from app.mattermost_client import MattermostClient
from app.models import Agent, Experiment, Org, Response, Task, ToolCall
from app.output_rendering import build_response_attachment
from app.tool_roster import build_tool_roster
from app.vault import decrypt

logger = logging.getLogger(__name__)
router = APIRouter()

# docs/05-ux-behavior.md Section 4: reserved *only* for "requires expert
# review" content, never reused for any other purpose, so a reviewer can
# scan a channel and immediately spot which messages need sign-off.
EXPERT_REVIEW_COLOR = "#D72638"


async def _resolve_or_create_experiment(db: AsyncSession, org_id, agent_id, channel_id: str) -> Experiment:
    """The current open Experiment for this Mattermost channel -- the most
    recent status='active' row. Auto-creates one (name=None, shown to the
    researcher as "Untitled experiment") if none exists, so a plain message
    never has to wait on a /experiment start first. See the Experiments plan
    -- this sidesteps Mattermost's outgoing-webhook payload having no
    thread-root field at all (confirmed against Mattermost's own docs),
    which ruled out inferring boundaries from thread structure.
    """
    result = await db.execute(
        select(Experiment)
        .where(Experiment.channel_id == channel_id, Experiment.status == "active")
        .order_by(Experiment.created_at.desc())
        .limit(1)
    )
    experiment = result.scalars().first()
    if experiment is not None:
        return experiment

    experiment = Experiment(org_id=org_id, agent_id=agent_id, channel_id=channel_id, name=None, folder_path="")
    db.add(experiment)
    await db.flush()  # assigns experiment.id before the folder path can use it
    folder = Path(settings.experiments_dir) / str(experiment.id)
    folder.mkdir(parents=True, exist_ok=True)
    experiment.folder_path = str(folder)
    return experiment


async def _build_conversation_history(db: AsyncSession, experiment_id) -> list[str]:
    """Prior turns in this experiment, oldest first, as plain-text
    "Researcher: ...\\nAgent: ..." entries -- see run_agent's
    conversation_history param in claude_runner.py. Plain text, no
    summarization/compaction yet; that's a later concern if transcripts get
    long."""
    result = await db.execute(
        select(Task)
        .where(Task.experiment_id == experiment_id, Task.status == "completed")
        .order_by(Task.created_at)
    )
    prior_tasks = result.scalars().all()

    history = []
    for t in prior_tasks:
        resp_result = await db.execute(
            select(Response).where(Response.task_id == t.id).order_by(Response.created_at.desc()).limit(1)
        )
        resp = resp_result.scalars().first()
        entry = f"Researcher: {t.raw_request}"
        if resp is not None:
            entry += f"\nAgent: {resp.body}"
        history.append(entry)
    return history


async def _run_agent_and_respond(task_id, agent_id: str, channel_id: str, user_message: str, experiment_id) -> None:
    """Runs in the background, after the webhook has already returned a
    receipt to Mattermost. Owns its own DB session -- the request-scoped
    one from the original call is closed by the time this runs."""
    async with async_session() as db:
        agent = await db.get(Agent, agent_id)
        task = await db.get(Task, task_id)
        experiment = await db.get(Experiment, experiment_id)
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
            roster = await build_tool_roster(db, agent)

            async def on_plan(plan_text: str) -> None:
                await mm.post_message(channel_id, f"**Plan:**\n{plan_text}")

            # Sets the contextvar in-process/in-Camofox tools (download_paper
            # etc, app/tools/literature_discovery.py) read via
            # app/experiment_context.py -- set here, before run_agent, so it's
            # active for the whole task tree run_agent spawns (contextvars
            # propagate to child asyncio tasks created from within this one).
            # See the Experiments plan.
            conversation_history = await _build_conversation_history(db, experiment_id)
            exp_dir = Path(experiment.folder_path) if experiment is not None else None
            current_experiment_dir.set(exp_dir)

            try:
                result = await run_agent(
                    user_message, roster, on_plan=on_plan,
                    conversation_history=conversation_history,
                    cwd=experiment.folder_path if experiment is not None else None,
                )
            except Exception:
                logger.exception("Agent run failed for task %s", task_id)
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
            # (docs/06-data-model.md), mapped back to the right ToolSource via
            # the roster -- generalized past the Phase 1 PubMed-only version,
            # since the roster can now span multiple tool sources.
            tool_call_rows: list[ToolCall] = []
            for tc in result.tool_calls:
                tool_source = roster.tool_source_by_mcp_name.get(tc.mcp_server_name)
                if tool_source is None:
                    logger.warning("Tool call from unknown mcp server %r; skipping ToolCall row.", tc.mcp_server_name)
                    continue
                row = ToolCall(
                    task_id=task_id,
                    tool_source_id=tool_source.id,
                    request_payload=tc.request,
                    response_payload={"text": tc.result_text},
                    status="ok",
                )
                db.add(row)
                tool_call_rows.append(row)
            if tool_call_rows:
                await db.flush()  # assigns .id to each row before citations reference them

            # Map each citation's tool_call_index (an index into result.tool_calls)
            # to the corresponding persisted row -- skipped tool calls (unknown
            # mcp server) would desync a simple positional list, so build an
            # explicit index map instead of assuming 1:1 ordering.
            persisted_by_original_index = {}
            row_i = 0
            for orig_i, tc in enumerate(result.tool_calls):
                if roster.tool_source_by_mcp_name.get(tc.mcp_server_name) is not None:
                    persisted_by_original_index[orig_i] = tool_call_rows[row_i]
                    row_i += 1

            citations = [
                Citation(
                    tool_call_id=persisted_by_original_index[c.tool_call_index].id,
                    citation_label=c.label,
                    record_ref=c.record_ref,
                )
                for c in result.citations
                if c.tool_call_index in persisted_by_original_index
            ]

            # grounding.py's create_response() raises if provenance_type is
            # "grounded" without >=1 citation -- the roster-mapping filter
            # above can (rarely) drop every citation the runner found (an
            # unrecognized mcp server), so recompute provenance from what
            # actually survived filtering rather than trusting the runner's
            # own (pre-filter) judgment.
            final_provenance = "grounded" if citations else "synthesis" if result.body else "ungroundable"

            # Flagged by *which tool sources contributed to the grounding*
            # (docs/05-ux-behavior.md Section 4), not by which tool was
            # merely called -- a source consulted but not actually cited
            # doesn't trigger this.
            requires_review = any(
                roster.tool_source_by_mcp_name.get(
                    result.tool_calls[c.tool_call_index].mcp_server_name
                ).requires_expert_review
                for c in result.citations
                if c.tool_call_index in persisted_by_original_index
            )

            response = await create_response(
                db,
                task_id=task_id,
                body=result.body,
                provenance_type=final_provenance,
                citations=citations or None,
                requires_expert_review=requires_review,
            )
            # docs/05-ux-behavior.md Section 3: short output renders in
            # full inline; a large table gets a summary + a link to the
            # full report (app/routers/reports.py) instead of a long raw
            # markdown table dumped into chat.
            report_url = f"{settings.orchestrator_public_url}/reports/{response.id}"
            attachment = build_response_attachment(
                result.body, report_url, color=EXPERT_REVIEW_COLOR if requires_review else None
            )
            if requires_review:
                attachment["pretext"] = "⚠️ **Requires expert review**"
            posted = await mm.post_message(channel_id, "", attachments=[attachment])
            response.mattermost_message_id = posted.get("id")

            # FR-10, docs/10-build-plan.md Phase 4: the human-facing surface
            # of the TOOL_CALL table -- every response also gets a compact
            # audit summary in #grounding-log, if the org has one configured.
            org = await db.get(Org, agent.org_id)
            if org is not None and org.grounding_log_channel_id:
                tool_names_used = sorted(
                    {
                        roster.tool_source_by_mcp_name[tc.mcp_server_name].name
                        for tc in result.tool_calls
                        if roster.tool_source_by_mcp_name.get(tc.mcp_server_name) is not None
                    }
                )
                audit_lines = [
                    f"**Task** `{task_id}` -- provenance: `{final_provenance}`"
                    + (" -- ⚠️ requires expert review" if requires_review else ""),
                    f"Tool sources used: {', '.join(tool_names_used) or 'none'}",
                    f"Citations ({len(citations)}): {', '.join(c.record_ref for c in citations) or 'none'}",
                ]
                await mm.post_message(org.grounding_log_channel_id, "\n".join(audit_lines))

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

    # There is exactly one master AGENT per org (docs/07-system-architecture.md
    # pivot note) -- no per-domain routing decision to make here anymore.
    result = await db.execute(select(Agent).where(Agent.active.is_(True)).limit(1))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail="No active agent registered yet -- run scripts/seed_dev_data.py.",
        )

    experiment = await _resolve_or_create_experiment(db, agent.org_id, agent.id, channel_id)

    task = Task(
        org_id=agent.org_id,
        agent_id=agent.id,
        experiment_id=experiment.id,
        mattermost_thread_id=post_id,
        requested_by_user_id=user_id,
        status="running",
        raw_request=text,
    )
    db.add(task)
    await db.commit()

    background_tasks.add_task(
        _run_agent_and_respond, task.id, str(agent.id), channel_id, text, experiment.id
    )

    # Synchronous receipt only (docs/05-ux-behavior.md Section 1) -- the
    # plan and the final report are both posted asynchronously as the
    # background run produces them.
    return {"text": f"🔎 Looking into this, @{user_name} -- one moment...", "response_type": "in_channel"}


@router.post("/webhooks/mattermost/experiment")
async def mattermost_experiment_command(
    db: AsyncSession = Depends(get_db),
    token: str = Form(...),
    channel_id: str = Form(...),
    text: str = Form(""),
):
    """The explicit half of the experiment-boundary design (see the
    Experiments plan): `/experiment start ["name"]` / `end` / `status`.
    Registered as a Mattermost Slash Command -- same form-encoded POST shape
    as the outgoing webhook above, confirmed against Mattermost's own docs.
    A plain @orchestrator message still auto-opens an experiment on its own
    (_resolve_or_create_experiment) if none is open; this route is for
    explicit control, not a required step.
    """
    if settings.mattermost_webhook_secret and token != settings.mattermost_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid webhook token")

    result = await db.execute(select(Agent).where(Agent.active.is_(True)).limit(1))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=503, detail="No active agent registered yet -- run scripts/seed_dev_data.py."
        )

    parts = text.strip().split(maxsplit=1)
    subcommand = parts[0].lower() if parts else "status"
    arg = parts[1].strip() if len(parts) > 1 else ""

    async def _current_active() -> Experiment | None:
        r = await db.execute(
            select(Experiment)
            .where(Experiment.channel_id == channel_id, Experiment.status == "active")
            .order_by(Experiment.created_at.desc())
            .limit(1)
        )
        return r.scalars().first()

    if subcommand == "start":
        # Only one open experiment per channel -- starting a new one closes
        # whatever was open (there should be at most one anyway, since every
        # path that opens one checks for an existing active row first, but
        # closing any stragglers here keeps that invariant even if it's ever
        # violated).
        r = await db.execute(
            select(Experiment).where(Experiment.channel_id == channel_id, Experiment.status == "active")
        )
        for stale in r.scalars().all():
            stale.status = "closed"
            stale.closed_at = datetime.now(timezone.utc)

        name = arg.strip('"').strip() or None
        experiment = Experiment(org_id=agent.org_id, agent_id=agent.id, channel_id=channel_id, name=name, folder_path="")
        db.add(experiment)
        await db.flush()
        folder = Path(settings.experiments_dir) / str(experiment.id)
        folder.mkdir(parents=True, exist_ok=True)
        experiment.folder_path = str(folder)
        await db.commit()
        label = name or "Untitled experiment"
        return {"text": f"🧪 Started experiment **{label}** (`{experiment.id}`).", "response_type": "in_channel"}

    if subcommand == "end":
        experiment = await _current_active()
        if experiment is None:
            return {"text": "No experiment is currently open in this channel.", "response_type": "ephemeral"}
        experiment.status = "closed"
        experiment.closed_at = datetime.now(timezone.utc)
        await db.commit()
        label = experiment.name or "Untitled experiment"
        return {"text": f"🧪 Closed experiment **{label}**.", "response_type": "in_channel"}

    if subcommand == "status":
        experiment = await _current_active()
        if experiment is None:
            return {
                "text": "No experiment is currently open in this channel -- one will auto-open on your next message.",
                "response_type": "ephemeral",
            }
        label = experiment.name or "Untitled experiment"
        task_count_result = await db.execute(select(func.count(Task.id)).where(Task.experiment_id == experiment.id))
        task_count = task_count_result.scalar_one()
        papers_path = Path(experiment.folder_path) / "papers"
        paper_count = len(list(papers_path.glob("*.pdf"))) if papers_path.is_dir() else 0
        return {
            "text": (
                f"🧪 Current experiment: **{label}** (`{experiment.id}`)\n"
                f"- Messages: {task_count}\n"
                f"- Papers downloaded: {paper_count}\n"
                f"- Folder: `{experiment.folder_path}`"
            ),
            "response_type": "ephemeral",
        }

    return {
        "text": 'Usage: `/experiment start ["name"]`, `/experiment end`, `/experiment status`',
        "response_type": "ephemeral",
    }
