"""Shared persistence for a claude_runner.run_agent() RunnerResult -- turns
its real tool calls and citations into ToolCall/GroundingLink/Response rows
through grounding.py's create_response() gate. Extracted out of
app/routers/mattermost_webhook.py's inline block (multi-stage research
pipeline plan) so app/landscape_scan.py can reuse the exact same
persistence path instead of duplicating it -- the Landscape Scan's own
Task/Response get real ToolCall rows and real citation/grounding treatment
this way, not a hand-rolled approximation.
"""
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.claude_runner import RunnerResult
from app.grounding import Citation, create_response
from app.models import Response, ToolCall
from app.tool_roster import ToolRoster

logger = logging.getLogger(__name__)


@dataclass
class PersistedAgentRun:
    response: Response
    tool_call_rows: list[ToolCall]
    citations: list[Citation]
    tool_names_used: list[str]
    requires_review: bool
    final_provenance: str


async def persist_agent_run(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    roster: ToolRoster,
    result: RunnerResult,
    mattermost_message_id: str | None = None,
) -> PersistedAgentRun:
    """Persists every real tool call the runner made as a ToolCall row,
    maps each surviving citation to its persisted row, and creates the
    Response through grounding.py's gate. Recomputes provenance from what
    actually survives the roster-mapping filter below (an unrecognized mcp
    server can, rarely, drop every citation the runner found) rather than
    trusting the runner's own pre-filter judgment -- same logic
    mattermost_webhook.py used inline before this was extracted."""
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

    final_provenance = "grounded" if citations else "synthesis" if result.body else "ungroundable"

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
        mattermost_message_id=mattermost_message_id,
        requires_expert_review=requires_review,
    )

    tool_names_used = sorted({
        roster.tool_source_by_mcp_name[tc.mcp_server_name].name
        for tc in result.tool_calls
        if roster.tool_source_by_mcp_name.get(tc.mcp_server_name) is not None
    })

    return PersistedAgentRun(
        response=response, tool_call_rows=tool_call_rows, citations=citations,
        tool_names_used=tool_names_used, requires_review=requires_review, final_provenance=final_provenance,
    )
