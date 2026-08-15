"""A real ClinicalTrials.gov MCP tool (docs/10-build-plan.md Phase 3,
Shortlist #6), same in-process pattern as the other tools --
ClinicalTrials.gov's REST API v2 is free and unauthenticated.

One tool: search registered trials by free text and return each trial's
NCT ID, title, status, phase, and conditions. Trial-registry data is
clinical/regulatory-sensitive (docs/05-ux-behavior.md Section 4) -- this
tool source is marked requires_expert_review=True in
scripts/seed_dev_data.py, so any response grounded through it gets the
"requires expert review" marker when posted.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"


@tool(
    "search_trials",
    "Search ClinicalTrials.gov for registered trials matching a free-text "
    "query (e.g. a drug, gene, or condition -- combine terms with AND/OR "
    "and quote phrases for precision). Returns each trial's NCT ID, "
    "title, status, phase, and conditions. Use the NCT ID as the citable "
    "record reference -- never invent one or state a trial detail this "
    "tool didn't return.",
    {"query": str, "max_results": int},
)
async def search_trials(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 20)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            CTGOV_URL,
            params={
                "query.term": args["query"],
                "pageSize": max_results,
                "fields": "NCTId,BriefTitle,OverallStatus,Phase,Condition",
            },
        )
        resp.raise_for_status()
        studies = resp.json().get("studies", [])

    if not studies:
        return {"content": [{"type": "text", "text": f"No ClinicalTrials.gov trials found for {args['query']!r}."}]}

    lines = []
    for s in studies:
        proto = s.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {}).get("overallStatus", "unknown status")
        phases = ", ".join(proto.get("designModule", {}).get("phases", [])) or "phase not specified"
        conditions = ", ".join(proto.get("conditionsModule", {}).get("conditions", []))
        lines.append(
            f"- NCT ID {ident.get('nctId')}: {ident.get('briefTitle', '')} "
            f"({status}, {phases}) -- conditions: {conditions or 'not specified'}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_clinicaltrials_mcp_server():
    return create_sdk_mcp_server(name="clinicaltrials", tools=[search_trials])
