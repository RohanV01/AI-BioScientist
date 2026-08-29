"""Reproducibility export (docs/18-platform-capability-gaps.md Pass 1
#5): the platform's whole mission is "every claim traces to a real
tool call," but until now that trail existed only in the DB, with no
button to package it as portable supplementary material. This packages
one Response's full evidence trail -- every tool call on its Task
(request payload, response payload, status, timestamp), plus every
citation tying a GroundingLink back to the exact tool call that
produced it -- into one JSON document. Pure DB query + serialization,
no external network call, same shape as `app/methods_report.py`.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GroundingLink, Response, Task, ToolCall, ToolSource


class ResponseNotFound(ValueError):
    pass


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def generate_reproducibility_bundle(db: AsyncSession, response_id: uuid.UUID) -> dict[str, Any]:
    """Real, portable evidence trail for one Response: its own task's
    request, every tool call made on that task (real request/response
    payloads, not summarized), and every citation this specific
    response actually relied on, cross-referenced to the tool call that
    produced it. Scoped to the Response's own Task, not the whole
    Experiment -- a reproducibility bundle is about one conclusion, not
    an entire investigation (that's what the Methods section is for)."""
    response = await db.get(Response, response_id)
    if response is None:
        raise ResponseNotFound(f"No response found with id {response_id}")

    task = await db.get(Task, response.task_id)

    tool_call_stmt = (
        select(ToolCall, ToolSource.name)
        .join(ToolSource, ToolCall.tool_source_id == ToolSource.id)
        .where(ToolCall.task_id == response.task_id)
        .order_by(ToolCall.called_at)
    )
    tool_call_rows = (await db.execute(tool_call_stmt)).all()

    grounding_stmt = select(GroundingLink).where(GroundingLink.response_id == response_id)
    grounding_links = (await db.execute(grounding_stmt)).scalars().all()
    citations_by_tool_call: dict[uuid.UUID, list[dict[str, str]]] = {}
    for link in grounding_links:
        citations_by_tool_call.setdefault(link.tool_call_id, []).append(
            {"citation_label": link.citation_label, "record_ref": link.record_ref}
        )

    tool_calls_bundle = []
    for tool_call, tool_source_name in tool_call_rows:
        tool_calls_bundle.append(
            {
                "tool_call_id": str(tool_call.id),
                "tool_source": tool_source_name,
                "status": tool_call.status,
                "called_at": _iso(tool_call.called_at),
                "request_payload": tool_call.request_payload,
                "response_payload": tool_call.response_payload,
                "cited_by_this_response": citations_by_tool_call.get(tool_call.id, []),
            }
        )

    return {
        "response_id": str(response.id),
        "provenance_type": response.provenance_type,
        "requires_expert_review": response.requires_expert_review,
        "response_body": response.body,
        "response_created_at": _iso(response.created_at),
        "task": {
            "task_id": str(task.id) if task else None,
            "raw_request": task.raw_request if task else None,
            "requested_by_user_id": task.requested_by_user_id if task else None,
            "created_at": _iso(task.created_at) if task else None,
        },
        "tool_calls": tool_calls_bundle,
        "total_tool_calls": len(tool_calls_bundle),
        "total_citations": len(grounding_links),
    }
