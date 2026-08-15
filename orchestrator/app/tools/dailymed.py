"""A real DailyMed MCP tool (docs/10-build-plan.md Phase 3, Shortlist
#6), same in-process pattern as the other tools -- NLM's DailyMed REST
API (structured FDA drug labels) is free and unauthenticated.

One tool: search DailyMed for a drug's official label (SPL) and return
its set ID, title, and published date, plus the resolvable label URL.
Drug-label data is clinical/regulatory-sensitive
(docs/05-ux-behavior.md Section 4) -- this tool source is marked
requires_expert_review=True in scripts/seed_dev_data.py.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"


@tool(
    "search_drug_labels",
    "Search DailyMed for a drug's official FDA label (Structured Product "
    "Label) by drug name. Returns each label's set ID, title, and "
    "published date, with a resolvable URL to the full label. Use the "
    "set ID as the citable record reference -- never invent one or state "
    "a label detail this tool didn't return.",
    {"drug_name": str, "max_results": int},
)
async def search_drug_labels(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            DAILYMED_URL, params={"drug_name": args["drug_name"], "pagesize": max_results}
        )
        resp.raise_for_status()
        entries = resp.json().get("data", [])

    if not entries:
        return {"content": [{"type": "text", "text": f"No DailyMed labels found for {args['drug_name']!r}."}]}

    lines = []
    for e in entries:
        setid = e["setid"]
        lines.append(
            f"- DailyMed set ID {setid}: {e.get('title', '')} "
            f"(published {e.get('published_date', 'unknown date')}) -- "
            f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_dailymed_mcp_server():
    return create_sdk_mcp_server(name="dailymed", tools=[search_drug_labels])
