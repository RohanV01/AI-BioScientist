"""MCP tool wrapping app/memory/retrieve.py's recall_prior_findings for the
Landscape Scan stage (app/landscape_scan.py) -- the read side of the
cross-experiment Memory layer (docs/18-platform-capability-gaps.md Pass 1
#1). The first in-process tool in this codebase to open its own DB session
rather than reading local experiment files/contextvars: recall is
deliberately cross-experiment ("has anyone here looked at this before,
anywhere"), so there's no per-experiment folder to scope it to the way
papers_dir()/uploads_dir() do.

Each recalled fact is returned tagged `[memory_fact:<source_task_id>]` --
the same methodological-citation-tag convention app/claude_runner.py's
RECORD_REF_PATTERNS already uses for local-computation tools
([vina:...], [cobra:...]) -- so a recalled fact stays traceable to the real
Task/Response that originally produced it, and grounding.py's citation
verification (the record_ref must appear in this tool call's own
response_payload) holds the same way it does for every other tool.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.db import async_session
from app.memory.retrieve import recall_prior_findings


@tool(
    "recall_prior_findings",
    "Search this platform's own memory of everything it has previously "
    "found and concluded, across every past experiment -- not external "
    "databases, but this platform's own prior grounded findings. Call this "
    "during a landscape scan to check whether a topic has already been "
    "investigated before proposing to re-discover it. Pass a plain-text "
    "topic/question, and optionally a list of specific entity identifiers "
    "(gene symbols, ChEMBL IDs, etc.) if already known.",
    {"query_text": str, "entity_refs": list},
)
async def recall_prior_findings_tool(args: dict[str, Any]) -> dict[str, Any]:
    entity_refs = args.get("entity_refs") or []
    async with async_session() as db:
        facts = await recall_prior_findings(db, query_text=args["query_text"], entity_refs=entity_refs)

    if not facts:
        return {
            "content": [{
                "type": "text",
                "text": "No prior findings in this platform's memory match this topic -- "
                        "this appears to be new ground for this platform.",
            }]
        }

    lines = [f"Prior findings from this platform's own memory -- {len(facts)} result(s):"]
    for fact in facts:
        lines.append(f"- ({fact.entity_ref}) {fact.statement} [memory_fact:{fact.source_task_id}]")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_memory_recall_mcp_server():
    return create_sdk_mcp_server(name="memory_recall", tools=[recall_prior_findings_tool])
