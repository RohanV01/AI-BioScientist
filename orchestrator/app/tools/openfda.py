"""A real openFDA MCP tool (docs/17-remaining-tools-wiring-plan.md's
"newly identified gaps" section) -- the FDA's own free, unauthenticated
REST API over FAERS (FDA Adverse Event Reporting System) real-world
adverse-event reports. Complements `dailymed.py` (drug label text --
what a drug is *approved to claim*) with a genuinely different signal:
what's actually been reported in practice.

Confirmed the real API contract live before wiring (2026-08-26):
GET /drug/event.json?search=patient.drug.medicinalproduct:<name>&limit=<n>.
"""
from collections import Counter
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

OPENFDA_BASE = "https://api.fda.gov/drug/event.json"


@tool(
    "search_adverse_events",
    "Search openFDA's FAERS database for real-world adverse-event reports "
    "involving a drug (by medicinal product name). Returns the total "
    "report count and the most frequently reported reactions across the "
    "sampled reports. Complements dailymed.py's label text (what's "
    "approved) with what's actually been reported. Never state a "
    "reaction/count this tool didn't actually return.",
    {"drug_name": str, "max_reports": int},
)
async def search_adverse_events(args: dict[str, Any]) -> dict[str, Any]:
    drug_name = (args.get("drug_name") or "").strip()
    max_reports = min(int(args.get("max_reports", 50)), 100)
    if not drug_name:
        return {"content": [{"type": "text", "text": "drug_name must be non-empty."}]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            OPENFDA_BASE,
            params={"search": f"patient.drug.medicinalproduct:{drug_name}", "limit": max_reports},
        )
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No openFDA adverse-event reports found for {drug_name!r}."}]}
        resp.raise_for_status()
        data = resp.json()

    total = data.get("meta", {}).get("results", {}).get("total", 0)
    reports = data.get("results", [])
    if not reports:
        return {"content": [{"type": "text", "text": f"No openFDA adverse-event reports found for {drug_name!r}."}]}

    reaction_counts: Counter[str] = Counter()
    for r in reports:
        for reaction in r.get("patient", {}).get("reaction", []):
            term = reaction.get("reactionmeddrapt")
            if term:
                reaction_counts[term] += 1

    # [openfda:drug_name] is the citable unit -- FAERS aggregate report
    # counts have no single per-record ID (each underlying report does,
    # but the value here is the aggregate), same methodological-citation
    # convention as gseapy's [gseapy:library] tag.
    lines = [
        f"openFDA FAERS [openfda:{drug_name}]: {total} total adverse-event reports mention {drug_name!r} "
        f"(showing reaction frequency across {len(reports)} sampled reports):"
    ]
    for term, count in reaction_counts.most_common(15):
        lines.append(f"- {term}: {count}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_openfda_mcp_server():
    return create_sdk_mcp_server(name="openfda", tools=[search_adverse_events])
