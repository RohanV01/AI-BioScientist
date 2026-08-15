"""A real Open Targets MCP tool, built the same way as
app/tools/pubmed.py and app/tools/chembl.py: in-process via the Claude
Agent SDK's @tool/create_sdk_mcp_server, hitting Open Targets' free
public GraphQL API directly -- no separate server process, no auth.

Two tools: search_entities (find a target by gene symbol, get its
Ensembl ID) and get_target_disease_associations (genetic-evidence-backed
disease associations for a target, with scores) -- covers the
target-identification-and-validation path that's the highest-value
Open Targets use case in the research report.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"


async def _graphql(query: str, variables: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(OT_URL, json={"query": query, "variables": variables})
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Open Targets GraphQL error: {data['errors']}")
        return data["data"]


@tool(
    "search_entities",
    "Search Open Targets for a target (gene) by symbol or name. Returns "
    "the Ensembl gene ID needed for further Open Targets lookups -- use "
    "this ID as the citable record reference, never invent one.",
    {"query": str, "max_results": int},
)
async def search_entities(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    data = await _graphql(
        "query($q: String!) { search(queryString: $q, entityNames: [\"target\"]) "
        "{ hits { id name entity } } }",
        {"q": args["query"]},
    )
    hits = data["search"]["hits"][:max_results]
    if not hits:
        return {"content": [{"type": "text", "text": f"No Open Targets entities found for {args['query']!r}."}]}
    lines = [f"- Ensembl ID {h['id']}: {h['name']} ({h['entity']})" for h in hits]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_target_disease_associations",
    "Given an Ensembl gene ID (from search_entities), return Open "
    "Targets' genetic-evidence-backed disease associations, ranked by "
    "score. Use the disease IDs/names and scores this returns as citable "
    "facts -- never state an association or score this tool didn't "
    "return.",
    {"ensembl_id": str, "max_results": int},
)
async def get_target_disease_associations(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 10)), 25)
    data = await _graphql(
        "query($id: String!, $size: Int!) { target(ensemblId: $id) { id approvedSymbol "
        "associatedDiseases(page: {index: 0, size: $size}) { count rows { disease { id name } score } } } }",
        {"id": args["ensembl_id"], "size": max_results},
    )
    target = data.get("target")
    if target is None:
        return {"content": [{"type": "text", "text": f"No Open Targets record found for Ensembl ID {args['ensembl_id']!r}."}]}

    assoc = target["associatedDiseases"]
    lines = [
        f"Disease associations for {target['approvedSymbol']} ({target['id']}) "
        f"({assoc['count']} total, showing {len(assoc['rows'])}):"
    ]
    for row in assoc["rows"]:
        lines.append(f"- {row['disease']['name']} ({row['disease']['id']}): association score {row['score']:.3f}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_open_targets_mcp_server():
    return create_sdk_mcp_server(
        name="open_targets", tools=[search_entities, get_target_disease_associations]
    )
