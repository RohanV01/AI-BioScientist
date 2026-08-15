"""A real PubMed MCP tool, built in-process with the Claude Agent SDK's
`@tool`/`create_sdk_mcp_server` mechanism rather than shelling out to a
separate MCP server process -- NCBI's E-utilities API is free/public/no-auth,
so there's no reason to run a whole extra process for it.

Named `search_articles` to match the tool name already used throughout
docs/ (the research report's live PubMed MCP uses the same name) -- keeps
the Orchestrator's actual tool consistent with what's documented.
"""
from typing import Any, TypedDict

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class SearchArticlesInput(TypedDict):
    query: str
    max_results: int


@tool(
    "search_articles",
    "Search PubMed for articles matching a query. Returns PMID, title, "
    "authors, journal, and year for each match -- use these as citations, "
    "never invent a PMID or title that wasn't returned here.",
    {"query": str, "max_results": int},
)
async def search_articles(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    max_results = min(int(args.get("max_results", 5)), 20)

    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results},
        )
        search_resp.raise_for_status()
        pmids = search_resp.json().get("esearchresult", {}).get("idlist", [])

        if not pmids:
            return {"content": [{"type": "text", "text": "No PubMed results found for this query."}]}

        summary_resp = await client.get(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
        )
        summary_resp.raise_for_status()
        summary = summary_resp.json().get("result", {})

    articles = []
    for pmid in pmids:
        rec = summary.get(pmid)
        if not rec:
            continue
        authors = ", ".join(a.get("name", "") for a in rec.get("authors", [])[:3])
        articles.append(
            {
                "pmid": pmid,
                "title": rec.get("title", ""),
                "authors": authors,
                "journal": rec.get("fulljournalname", rec.get("source", "")),
                "year": (rec.get("pubdate", "") or "").split(" ")[0],
            }
        )

    lines = [
        f"- PMID {a['pmid']}: {a['title']} ({a['authors']}, {a['journal']}, {a['year']})"
        for a in articles
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "articles": articles}


def build_pubmed_mcp_server():
    return create_sdk_mcp_server(name="pubmed", tools=[search_articles])
