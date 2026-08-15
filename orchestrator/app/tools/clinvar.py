"""A real ClinVar MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
built the same way as app/tools/pubmed.py -- NCBI E-utilities, free and
unauthenticated, no separate server process needed.

One tool: search ClinVar for variants in a gene (optionally filtered by
a free-text clinical-significance/condition term) and return each
variant's ClinVar accession, name, clinical significance classification,
review status, and associated condition(s) -- the clinical-genomics
counterpart to Ensembl's gene-identity lookup and Open Targets'
disease-association scores.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@tool(
    "search_variants",
    "Search ClinVar for variants in a gene, optionally narrowed by a "
    "free-text term (e.g. a condition or 'pathogenic'). Returns each "
    "variant's ClinVar accession, name, clinical significance, review "
    "status, and associated condition(s). Use the ClinVar accession as "
    "the citable record reference -- never invent one or state a "
    "classification this tool didn't return.",
    {"gene": str, "term": str, "max_results": int},
)
async def search_variants(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 20)
    query = f"{args['gene']}[gene]"
    extra = (args.get("term") or "").strip()
    if extra:
        query += f" AND {extra}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params={"db": "clinvar", "term": query, "retmode": "json", "retmax": max_results},
        )
        search_resp.raise_for_status()
        uids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not uids:
            return {"content": [{"type": "text", "text": f"No ClinVar variants found for {query!r}."}]}

        summary_resp = await client.get(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(uids), "retmode": "json"},
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

    lines = []
    for uid in uids:
        rec = result.get(uid)
        if not rec:
            continue
        gc = rec.get("germline_classification") or {}
        conditions = ", ".join(
            t.get("trait_name", "") for t in gc.get("trait_set", []) if t.get("trait_name")
        )
        lines.append(
            f"- ClinVar {rec.get('accession', uid)}: {rec.get('title', '')} -- "
            f"classification: {gc.get('description', 'not classified')} "
            f"({gc.get('review_status', 'unknown review status')}); "
            f"condition(s): {conditions or 'not specified'}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_clinvar_mcp_server():
    return create_sdk_mcp_server(name="clinvar", tools=[search_variants])
