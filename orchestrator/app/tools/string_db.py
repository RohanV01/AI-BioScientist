"""A real STRING MCP tool (docs/10-build-plan.md Phase 3, Shortlist #5),
same in-process pattern as the other tools -- STRING's REST API is free
and unauthenticated. Module named string_db, not string, to avoid
shadowing the stdlib module.

One tool: given a gene/protein symbol, return its top known/predicted
interaction partners with STRING's combined confidence score --
protein-protein interaction data, distinct from KEGG's/Reactome's
curated pathway membership.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

STRING_URL = "https://string-db.org/api/json/interaction_partners"

# NCBI taxon IDs for the species STRING calls accept by name here --
# expand this if a query needs a species beyond human/mouse.
SPECIES_TAXON_IDS = {"human": 9606, "homo sapiens": 9606, "mouse": 10090, "mus musculus": 10090}


@tool(
    "get_interaction_partners",
    "Given a gene/protein symbol, return its top known/predicted "
    "interaction partners from STRING with a combined confidence score "
    "(0-1). Use the STRING ID as the citable record reference -- never "
    "invent an interaction this tool didn't return.",
    {"identifier": str, "species": str, "max_results": int},
)
async def get_interaction_partners(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 10)), 25)
    species_key = (args.get("species") or "human").strip().lower()
    taxon_id = SPECIES_TAXON_IDS.get(species_key, SPECIES_TAXON_IDS["human"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            STRING_URL,
            params={"identifiers": args["identifier"], "species": taxon_id, "limit": max_results},
        )
        # STRING returns 404 (not an empty list) for an unrecognized
        # identifier -- a normal empty result, not a real failure.
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No STRING interaction partners found for {args['identifier']!r}."}]}
        resp.raise_for_status()
        partners = resp.json()

    if not partners:
        return {"content": [{"type": "text", "text": f"No STRING interaction partners found for {args['identifier']!r}."}]}

    lines = []
    for p in partners:
        lines.append(
            f"- STRING {p['stringId_A']} <-> {p['stringId_B']}: "
            f"{p['preferredName_A']} interacts with {p['preferredName_B']} "
            f"(combined confidence score {p['score']:.3f})"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_string_mcp_server():
    return create_sdk_mcp_server(name="string", tools=[get_interaction_partners])
