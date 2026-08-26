"""A real Europe PMC MCP tool (docs/17-remaining-tools-wiring-plan.md's
"newly identified gaps" section) -- Europe PMC's REST API is free and
unauthenticated, and indexes a broader source set than PubMed alone
(pubmed.py): preprints (bioRxiv/medRxiv), grant/patent links, and
free-full-text availability signals PubMed's own index doesn't carry.

Confirmed the real API contract live before wiring (2026-08-26):
GET /webservices/rest/search?query=<q>&format=json&pageSize=<n>.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


@tool(
    "search_europepmc",
    "Search Europe PMC for articles/preprints matching a query. Broader "
    "source coverage than PubMed (pubmed.py's search_articles) -- "
    "includes bioRxiv/medRxiv preprints and free-full-text availability. "
    "Returns each hit's Europe PMC ID, source (MED=PubMed-indexed, "
    "PPR=preprint, PMC=full-text), title, authors, year, DOI, and whether "
    "free full text is available. Use the returned DOI/PMID as the "
    "citable reference, never invent one.",
    {"query": str, "max_results": int},
)
async def search_europepmc(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    max_results = min(int(args.get("max_results", 5)), 20)
    if not query:
        return {"content": [{"type": "text", "text": "query must be non-empty."}]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            EUROPEPMC_BASE,
            params={"query": query, "format": "json", "pageSize": max_results, "resultType": "lite"},
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("resultList", {}).get("result", [])
    total = data.get("hitCount", 0)
    if not results:
        return {"content": [{"type": "text", "text": f"No Europe PMC results found for {query!r}."}]}

    lines = [f"Europe PMC results for {query!r} ({total} total, showing {len(results)}):"]
    for r in results:
        # DOI and "PMID <n>" both already match existing RECORD_REF_PATTERNS
        # entries (claude_runner.py) -- prefer whichever is present so the
        # citation is actually extractable; a preprint-only Europe PMC ID
        # (e.g. "PPR123456") has no external cross-reference to cite yet.
        if r.get("doi"):
            ref = r["doi"]
        elif r.get("pmid"):
            ref = f"PMID {r['pmid']}"
        else:
            ref = f"Europe PMC ID {r.get('id')} (preprint, no PMID/DOI yet)"
        oa = "open access" if r.get("isOpenAccess") == "Y" else "not confirmed open access"
        lines.append(
            f"- [{r.get('source', 'n/a')}] {ref}: {r.get('title', 'no title')} "
            f"({r.get('authorString', 'no authors')}, {r.get('pubYear', 'n/a')}) -- {oa}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_europepmc_mcp_server():
    return create_sdk_mcp_server(name="europepmc", tools=[search_europepmc])
