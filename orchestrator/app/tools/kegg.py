"""A real KEGG MCP tool (docs/10-build-plan.md Phase 3, Shortlist #5),
same in-process pattern as the other tools -- KEGG's REST API is free
and unauthenticated (flat text, not JSON).

One tool: given a human gene symbol, return the KEGG pathways it
participates in -- the systems-biology counterpart to Open Targets'
disease associations and STRING's interaction partners.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

KEGG_URL = "https://rest.kegg.jp"


@tool(
    "get_gene_pathways",
    "Given a human gene symbol, return the KEGG pathways it's annotated "
    "as participating in. Use the KEGG pathway ID as the citable record "
    "reference -- never invent one or state a pathway this tool didn't "
    "return.",
    {"gene_symbol": str},
)
async def get_gene_pathways(args: dict[str, Any]) -> dict[str, Any]:
    symbol = args["gene_symbol"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{KEGG_URL}/get/hsa:{symbol}")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No KEGG entry found for human gene {symbol!r}."}]}
        resp.raise_for_status()
        text = resp.text

    pathways = []
    in_pathway_block = False
    for line in text.splitlines():
        if line.startswith("PATHWAY"):
            in_pathway_block = True
            line = line[len("PATHWAY"):]
        elif line and not line.startswith(" "):
            in_pathway_block = False
        if in_pathway_block:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                pathways.append((parts[0], parts[1]))

    if not pathways:
        return {"content": [{"type": "text", "text": f"No KEGG pathway annotations found for {symbol!r}."}]}
    lines = [f"- KEGG {pid}: {name}" for pid, name in pathways]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_kegg_mcp_server():
    return create_sdk_mcp_server(name="kegg", tools=[get_gene_pathways])
