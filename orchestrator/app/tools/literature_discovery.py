"""Literature Discovery & Acquisition (docs/10-build-plan.md Phase 3
backlog): the "crazy querying mechanism" from the user's own framing --
search a topic across all of scholarship (OpenAlex, not just PubMed),
then run the resulting DOIs through a fast local Sci-Hub archive check
to see which ones can actually be pulled full-text, rather than
bulk-importing the 32GB scihub.sql dump (rejected in Phase 0: two tested
parsing approaches both projected 6.5-21 hours).

Two tools:
  - discover_papers: OpenAlex works search. OpenAlex indexes ~250M works
    across every field (not just biomedicine like PubMed) and returns
    genuine open-access status/URL per work -- so the open-access tier of
    the acquisition waterfall is answered by this tool alone.
  - check_scihub_availability: grep the local flat Sci-Hub DOI index (one
    DOI per line, ~88.3M lines) for an exact match. A hit means the paper
    is archived in Sci-Hub's scimag collection and resolvable at
    sci-hub.se/<doi> -- this is the fallback tier the user explicitly
    asked to keep in the acquisition waterfall (OA -> Sci-Hub), with the
    tier itself always disclosed alongside the link (provenance
    labeling, not source restriction, per that decision). **Gap 9 /
    Shortlist #10 compliance boundary**: this tool re-checks each DOI's
    OpenAlex open-access status itself before ever reporting Sci-Hub
    availability -- it doesn't just trust that the caller already ran
    discover_papers and filtered correctly. A DOI the corpus's raw
    Sci-Hub index would otherwise flag as "available" is reported as
    legally open access instead whenever one actually exists, since the
    corpus itself (the flat DOI list) carries no OA/licensing metadata
    of its own and can't be trusted alone to decide this.

Actually downloading/parsing full-text PDF bytes is a further step this
tool doesn't do -- it resolves *which* tier a paper is available from
and a link to it, which is what grounding a citation needs.
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.config import settings

OPENALEX_URL = "https://api.openalex.org/works"


def _strip_doi_prefix(doi: str) -> str:
    return doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()


@tool(
    "discover_papers",
    "Search all of scholarship (OpenAlex -- every field, not just "
    "biomedicine) for papers matching a topic. Returns each paper's DOI, "
    "title, year, primary field/subfield, and open-access status/URL if "
    "one exists. Use the returned DOIs as citable record references, and "
    "pass any DOI NOT already open access to check_scihub_availability "
    "before assuming it's unreachable.",
    {"query": str, "max_results": int},
)
async def discover_papers(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 10)), 25)
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            OPENALEX_URL,
            params={
                "search": args["query"],
                "per_page": max_results,
                "select": "doi,title,publication_year,open_access,primary_topic",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    if not results:
        return {"content": [{"type": "text", "text": f"No OpenAlex results found for {args['query']!r}."}]}

    lines = []
    for r in results:
        doi = _strip_doi_prefix(r.get("doi") or "")
        if not doi:
            continue
        oa = r.get("open_access") or {}
        subfield = ((r.get("primary_topic") or {}).get("subfield") or {}).get("display_name", "")
        oa_bit = f"open access, {oa.get('oa_status')}: {oa.get('oa_url')}" if oa.get("is_oa") else "not open access"
        lines.append(
            f"- DOI {doi}: {r.get('title', '')} ({r.get('publication_year', '')}, {subfield}) -- {oa_bit}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _run_grep(dois: list[str], index_path: Path) -> subprocess.CompletedProcess:
    # -F: fixed strings (DOIs aren't regex). -x: exact whole-line match, so
    # one DOI that's a prefix of another can't false-positive on -F's
    # default substring-within-line matching.
    #
    # Blocking subprocess.run() via asyncio.to_thread rather than
    # asyncio.create_subprocess_exec() -- the latter depends on the
    # running loop owning a SIGCHLD-based child watcher on the main
    # thread, which broke silently (non-0/1 returncode, empty stderr)
    # when this tool ran for real inside the orchestrator's uvicorn
    # process with the Claude Agent SDK's in-process tool dispatch, even
    # though it worked fine in a standalone script. to_thread sidesteps
    # that entirely.
    return subprocess.run(
        ["grep", "-F", "-x", "-f", "/dev/stdin", str(index_path)],
        input="\n".join(dois).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


async def _openalex_oa_batch(dois: list[str]) -> dict[str, dict]:
    """DOI -> its OpenAlex open_access dict, for whichever of the given
    DOIs OpenAlex has a record for. One batched request via OpenAlex's
    `filter=doi:a|b|c` syntax rather than one request per DOI."""
    if not dois:
        return {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            OPENALEX_URL,
            params={"filter": "doi:" + "|".join(dois), "select": "doi,open_access", "per_page": len(dois)},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    return {_strip_doi_prefix(r.get("doi") or ""): (r.get("open_access") or {}) for r in results}


async def _grep_scihub_index(dois: list[str]) -> set[str]:
    index_path = Path(settings.scihub_doi_index_path)
    if not index_path.is_file():
        raise RuntimeError(f"Sci-Hub DOI index not found at {index_path} -- check SCIHUB_DOI_INDEX_PATH.")

    result = await asyncio.to_thread(_run_grep, dois, index_path)
    # grep exits 1 (not an error here) when none of the patterns match.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"grep against Sci-Hub index failed: {result.stderr.decode(errors='replace')}")
    return {line for line in result.stdout.decode(errors="replace").splitlines() if line}


@tool(
    "check_scihub_availability",
    "Given a list of DOIs, check full-text availability. This tool "
    "checks OpenAlex open-access status itself first -- if a DOI turns "
    "out to be legally open access, it reports that instead of Sci-Hub, "
    "even if you didn't already check. Only DOIs that are genuinely not "
    "open access get checked against the local Sci-Hub index. Always "
    "label a Sci-Hub-sourced citation as Sci-Hub-tier, never as open "
    "access.",
    {"dois": list},
)
async def check_scihub_availability(args: dict[str, Any]) -> dict[str, Any]:
    dois = [_strip_doi_prefix(d) for d in args["dois"] if d][:50]
    if not dois:
        return {"content": [{"type": "text", "text": "No DOIs given to check."}]}

    # Gap 9 / Shortlist #10: never let the corpus's raw Sci-Hub index --
    # which carries no OA/licensing metadata of its own -- be the last
    # word on a DOI that's actually legally open access.
    oa_by_doi = await _openalex_oa_batch(dois)
    still_unknown = [d for d in dois if not (oa_by_doi.get(d) or {}).get("is_oa")]
    found = await _grep_scihub_index(still_unknown) if still_unknown else set()

    lines = []
    for doi in dois:
        oa = oa_by_doi.get(doi) or {}
        if oa.get("is_oa"):
            lines.append(
                f"- DOI {doi}: open access ({oa.get('oa_status')}) -- {oa.get('oa_url')} "
                "(prefer this over Sci-Hub)"
            )
        elif doi in found:
            lines.append(f"- DOI {doi}: available via Sci-Hub -- https://sci-hub.se/{doi}")
        else:
            lines.append(f"- DOI {doi}: not open access and not found in the Sci-Hub archive")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_literature_discovery_mcp_server():
    return create_sdk_mcp_server(
        name="literature_discovery", tools=[discover_papers, check_scihub_availability]
    )
