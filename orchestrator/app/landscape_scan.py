"""Landscape Scan stage (multi-stage research pipeline plan section 2) --
runs before the main Plan/Execute/Synthesize call, surveying everything
this platform can find out about a query's topic across both this
platform's own past findings (app/tools/memory_recall.py) and live
structured/literature sources, so the Planner doesn't propose re-discovering
what's already known.

A real agentic call -- claude_runner.run_agent() again, not a scripted tool
sequence -- but with app/tool_roster.py's bounded LANDSCAPE_SCAN_TOOL_NAMES
roster and this module's own narrow system prompt. Reuses run_agent()
itself (rather than reimplementing the streaming/citation-extraction logic)
and app/agent_persistence.py's persist_agent_run() (rather than reimplementing
ToolCall/Response persistence), so the Landscape Scan gets real ToolCall
rows and real citation/grounding treatment for free, same as any other
agent run in this platform.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_persistence import PersistedAgentRun, persist_agent_run
from app.claude_runner import run_agent
from app.memory.consolidate import consolidate_facts
from app.models import Agent, Task
from app.tool_roster import build_landscape_scan_roster

logger = logging.getLogger(__name__)

LANDSCAPE_SCAN_SYSTEM_PROMPT = """\
You are surveying the current state of knowledge on a research topic, \
before any experiment is planned or executed. Your job is NOT to answer the \
researcher's question -- it's to build a comprehensive picture of what is \
already known, contested, or unexplored about the topic(s) in their message.

1. Identify the specific entities/topics in the request (genes, compounds, \
diseases, pathways, etc. -- and anything in ingested file/link content \
provided as extra context, if any).
2. Call recall_prior_findings first, to check whether this platform has \
already investigated this topic in a past experiment.
3. Decide which of your other available tools (structured lookups across \
targets, compounds, variants, pathways, clinical data, plus literature via \
discover_papers) are relevant, and call as many as genuinely needed -- this \
is a real multi-tool survey, not one lookup. Do not call download_paper or \
any tool not available to you; only discover_papers is available for \
literature, never full-text acquisition.
4. Synthesize a comprehensive "current state of knowledge" perspective: \
what's established, what's contested between sources, and what's simply \
unknown or unexplored. Every claim must carry its record ID inline, same \
grounding discipline as any other response.

Do not execute any experiment, write any file, or attempt to answer the \
researcher's actual question -- that's the Planner's job, working from your \
summary. This is survey only.
"""


async def run_landscape_scan(
    db: AsyncSession,
    *,
    agent: Agent,
    main_task: Task,
    user_message: str,
    experiment_id: uuid.UUID,
    cwd: str | None = None,
) -> tuple[Task, PersistedAgentRun]:
    """Creates the Landscape Scan's own child Task (parent_task_id=
    main_task.id, stage="landscape_scan" -- multi-stage research pipeline
    plan section 6), runs it, persists it through the same grounding gate as
    any other Response, consolidates its findings into the cross-experiment
    Memory layer, and returns (landscape_task, persisted_run) -- the
    caller's `prior_stage_context` is persisted_run.response.body."""
    landscape_task = Task(
        org_id=agent.org_id, agent_id=agent.id, parent_task_id=main_task.id, experiment_id=experiment_id,
        mattermost_thread_id=main_task.mattermost_thread_id, requested_by_user_id=main_task.requested_by_user_id,
        stage="landscape_scan", raw_request=f"[landscape-scan] {user_message}", status="running",
    )
    db.add(landscape_task)
    await db.flush()  # assigns landscape_task.id

    roster = await build_landscape_scan_roster(db, agent)

    result = await run_agent(
        user_message, roster, cwd=cwd, system_prompt=LANDSCAPE_SCAN_SYSTEM_PROMPT,
    )

    persisted = await persist_agent_run(db, task_id=landscape_task.id, roster=roster, result=result)

    landscape_task.status = "completed"
    landscape_task.completed_at = datetime.now(timezone.utc)

    # Best-effort: a memory-consolidation failure (e.g. the LLM backend is
    # unreachable) must not discard the landscape scan's own already-
    # persisted synthesis/citations -- confirmed live during manual testing,
    # this previously killed the whole landscape scan (and, transitively,
    # the main answer) on a single LLM hiccup in this one write-back step.
    try:
        await consolidate_facts(db, response=persisted.response, task=landscape_task, experiment_id=experiment_id)
    except Exception:
        logger.exception(
            "Memory consolidation failed for landscape scan task %s; landscape scan result is unaffected.",
            landscape_task.id,
        )

    return landscape_task, persisted
