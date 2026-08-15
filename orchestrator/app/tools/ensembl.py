"""A real Ensembl MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
same in-process pattern as the other tools -- Ensembl's REST API is free
and unauthenticated.

One tool: resolve a gene symbol to its stable Ensembl gene ID plus
genomic coordinates and a description. This is the foundational lookup
other genomics tools (ClinVar, gnomAD, UniProt cross-refs) will build on
once they're wired -- not building speculative variant/paralog lookups
here ahead of anything that would actually use them.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

ENSEMBL_URL = "https://rest.ensembl.org"


@tool(
    "search_gene",
    "Resolve a gene symbol (e.g. 'EGFR', 'BRCA1') to its stable Ensembl "
    "gene ID, genomic location, and description. Use the returned "
    "Ensembl ID as the citable record reference -- never invent one.",
    {"symbol": str, "species": str},
)
async def search_gene(args: dict[str, Any]) -> dict[str, Any]:
    symbol = args["symbol"]
    species = args.get("species") or "homo_sapiens"

    async with httpx.AsyncClient(timeout=15.0) as client:
        xref_resp = await client.get(
            f"{ENSEMBL_URL}/xrefs/symbol/{species}/{symbol}",
            params={"content-type": "application/json"},
        )
        xref_resp.raise_for_status()
        gene_ids = [x["id"] for x in xref_resp.json() if x.get("type") == "gene"]
        if not gene_ids:
            return {"content": [{"type": "text", "text": f"No Ensembl gene found for symbol {symbol!r} in {species}."}]}

        lookup_resp = await client.get(
            f"{ENSEMBL_URL}/lookup/id/{gene_ids[0]}",
            params={"content-type": "application/json"},
        )
        lookup_resp.raise_for_status()
        gene = lookup_resp.json()

    text = (
        f"Ensembl Gene ID {gene['id']}: {gene.get('display_name', symbol)} "
        f"({gene.get('biotype', 'unknown biotype')}) -- "
        f"{gene.get('description', 'no description')}. "
        f"Location: {gene.get('seq_region_name')}:{gene.get('start')}-{gene.get('end')} "
        f"strand {gene.get('strand')}, assembly {gene.get('assembly_name')}."
    )
    return {"content": [{"type": "text", "text": text}]}


def build_ensembl_mcp_server():
    return create_sdk_mcp_server(name="ensembl", tools=[search_gene])
