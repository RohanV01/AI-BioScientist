"""A real UniProt MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
same in-process pattern as the other tools -- UniProt's REST API is free
and unauthenticated.

One tool: search UniProtKB for a protein (by gene symbol, protein name,
or free text) and return its accession, names, organism, and a short
function summary -- the protein-function-annotation counterpart to
app/tools/ensembl.py's gene-identity lookup.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"


@tool(
    "search_protein",
    "Search UniProtKB (by gene symbol, protein name, or free text) for "
    "matching reviewed proteins. Returns each hit's UniProt accession, "
    "protein/gene names, organism, and a short function summary. Use the "
    "accession as the citable record reference -- never invent one.",
    {"query": str, "organism": str, "max_results": int},
)
async def search_protein(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    organism = args.get("organism", "").strip()
    query = args["query"]
    if organism:
        query = f'({query}) AND organism_name:"{organism}"'

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            UNIPROT_URL,
            params={
                "query": query,
                "format": "json",
                "size": max_results,
                "fields": "accession,id,protein_name,gene_names,organism_name,cc_function",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    if not results:
        return {"content": [{"type": "text", "text": f"No UniProt entries found for {args['query']!r}."}]}

    lines = []
    for r in results:
        accession = r["primaryAccession"]
        name = r.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "")
        genes = ", ".join(g.get("geneName", {}).get("value", "") for g in r.get("genes", []) if g.get("geneName"))
        organism_name = r.get("organism", {}).get("scientificName", "")
        function_text = ""
        for c in r.get("comments", []):
            if c.get("commentType") == "FUNCTION" and c.get("texts"):
                function_text = c["texts"][0]["value"]
                break
        function_bit = f" -- {function_text[:280]}" if function_text else ""
        lines.append(f"- UniProt {accession}: {name} (gene {genes or 'n/a'}, {organism_name}){function_bit}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_uniprot_mcp_server():
    return create_sdk_mcp_server(name="uniprot", tools=[search_protein])
