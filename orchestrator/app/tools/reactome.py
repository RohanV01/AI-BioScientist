"""A real Reactome MCP tool (docs/10-build-plan.md Phase 3, Shortlist
#5), same in-process pattern as the other tools -- Reactome's Content
Service REST API is free and unauthenticated.

One tool: search Reactome for pathways matching a gene or free-text
query and return each hit's stable ID and a summary -- Reactome's
pathways carry detailed, curated reaction-level mechanism, which is
what distinguishes it from KEGG's higher-level pathway diagrams.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

REACTOME_SEARCH_URL = "https://reactome.org/ContentService/search/query"


@tool(
    "search_pathways",
    "Search Reactome for pathways matching a gene symbol or free-text "
    "query (human, unless another species is given). Returns each "
    "pathway's stable Reactome ID and a summary. Use the Reactome ID as "
    "the citable record reference -- never invent one or state a "
    "mechanism this tool didn't return.",
    {"query": str, "species": str, "max_results": int},
)
async def search_pathways(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    species = args.get("species") or "Homo sapiens"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            REACTOME_SEARCH_URL,
            params={"query": args["query"], "species": species, "types": "Pathway", "cluster": "true"},
        )
        # Reactome's search returns 404 (not an empty result list) when
        # nothing matches -- a normal empty result, not a real failure.
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No Reactome pathways found for {args['query']!r} in {species}."}]}
        resp.raise_for_status()
        results = resp.json().get("results", [])

    entries = []
    for group in results:
        entries.extend(group.get("entries", []))
    entries = entries[:max_results]

    if not entries:
        return {"content": [{"type": "text", "text": f"No Reactome pathways found for {args['query']!r} in {species}."}]}

    lines = []
    for e in entries:
        name = e.get("name", "").replace('<span class="highlighting" >', "").replace("</span>", "")
        summary = (e.get("summation") or "").replace('<span class="highlighting" >', "").replace("</span>", "")
        lines.append(f"- Reactome {e.get('stId', e.get('id'))}: {name} -- {summary[:280]}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_reactome_mcp_server():
    return create_sdk_mcp_server(name="reactome", tools=[search_pathways])
