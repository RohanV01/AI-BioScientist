"""A real RCSB PDB MCP tool (docs/10-build-plan.md Phase 3, Shortlist
#8), same in-process pattern as the other tools -- RCSB's Search and
GraphQL APIs are free and unauthenticated.

One tool: full-text search for experimentally determined structures and
return each hit's PDB ID, title, resolution, and experimental method.
Structure *lookup* only -- docking/folding inference is explicitly
deferred (this is "where Gap 7/compute first becomes unavoidable for
anything beyond simple structure lookup," per the build plan).
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
GRAPHQL_URL = "https://data.rcsb.org/graphql"

ENTRY_DETAILS_QUERY = """
query($ids: [String!]!) {
  entries(entry_ids: $ids) {
    rcsb_id
    struct { title }
    rcsb_entry_info { resolution_combined }
    exptl { method }
  }
}
"""


@tool(
    "search_structures",
    "Full-text search RCSB PDB for experimentally determined structures "
    "(e.g. a protein name plus a feature like 'kinase domain' or a "
    "bound ligand). Returns each hit's PDB ID, title, resolution, and "
    "experimental method. Use the PDB ID as the citable record "
    "reference -- never invent one.",
    {"query": str, "max_results": int},
)
async def search_structures(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.post(
            SEARCH_URL,
            json={
                "query": {"type": "terminal", "service": "full_text", "parameters": {"value": args["query"]}},
                "return_type": "entry",
                "request_options": {"paginate": {"start": 0, "rows": max_results}},
            },
        )
        if search_resp.status_code == 204:
            return {"content": [{"type": "text", "text": f"No PDB structures found for {args['query']!r}."}]}
        search_resp.raise_for_status()
        ids = [r["identifier"] for r in search_resp.json().get("result_set", [])]
        if not ids:
            return {"content": [{"type": "text", "text": f"No PDB structures found for {args['query']!r}."}]}

        detail_resp = await client.post(GRAPHQL_URL, json={"query": ENTRY_DETAILS_QUERY, "variables": {"ids": ids}})
        detail_resp.raise_for_status()
        entries = detail_resp.json()["data"]["entries"]

    entries_by_id = {e["rcsb_id"]: e for e in entries}
    lines = []
    for pdb_id in ids:
        e = entries_by_id.get(pdb_id)
        if e is None:
            continue
        title = e.get("struct", {}).get("title", "")
        resolution = (e.get("rcsb_entry_info") or {}).get("resolution_combined") or []
        res_bit = f"{resolution[0]} Å" if resolution else "n/a"
        methods = ", ".join(m.get("method", "") for m in e.get("exptl") or [])
        lines.append(f"- PDB {pdb_id}: {title} (resolution {res_bit}, method: {methods or 'unknown'})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pdb_mcp_server():
    return create_sdk_mcp_server(name="pdb", tools=[search_structures])
