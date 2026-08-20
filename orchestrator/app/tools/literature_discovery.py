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
from app.tools.telegram_scihub import try_telegram_scihub_bot

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


# How many downloads run concurrently -- bounded rather than unbounded
# asyncio.gather so a large result set (many discover_papers calls feeding
# one download_paper call) doesn't hammer Sci-Doc-Hub/Camofox with dozens
# of simultaneous requests at once.
_DOWNLOAD_CONCURRENCY = 5


def _doi_to_filename(doi: str) -> str:
    return doi.replace("/", "_") + ".pdf"


async def _try_sci_doc_hub(doi: str) -> bytes | None:
    """Primary full-text source: the Sci-Doc-Hub MCP server
    (https://github.com/JackKuo666/Sci-Hub-MCP-Server --
    Vault/Open-Source-Projects/sci-doc-hub-mcp-server-2026-08-11.md).
    Returns the PDF bytes, or None if unavailable/unreachable so the
    caller falls back to Camofox.
    """
    if not settings.sci_doc_hub_mcp_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # PLACEHOLDER -- fill in the Sci-Doc-Hub MCP server's actual
            # download endpoint/request shape once deployed.
            resp = await client.get(
                f"{settings.sci_doc_hub_mcp_url}",  # PLACEHOLDER endpoint path
                params={"doi": doi},
            )
            resp.raise_for_status()
            if "pdf" not in resp.headers.get("content-type", ""):
                return None
            return resp.content
    except httpx.HTTPError:
        return None


# A Sci-Hub *landing page* embeds the PDF directly (<embed>/<iframe src=...>)
# rather than triggering a real browser download -- confirmed against the
# live sci-hub.ren UI (paste a DOI/URL into "enter your reference", click
# "open", the resulting page just shows the PDF inline). So this reads the
# embedded src straight out of the DOM instead of watching for a download
# event.
_PDF_SRC_SCRIPT = (
    "(() => { const el = document.querySelector('embed, iframe'); "
    "return el ? el.getAttribute('src') : null; })()"
)


async def _try_camofox(doi: str) -> bytes | None:
    """Fallback full-text source when Sci-Doc-Hub fails/is unreachable:
    Camofox stealth headless browser
    (https://github.com/jo-inc/camofox-browser --
    Vault/AI-Tools/camofox-browser-stealth-headless-browser-2026-08-16.md).

    Camofox is a generic browser-automation REST API, not a paper-download
    endpoint, so this drives a real per-mirror tab lifecycle, trying each
    configured Sci-Hub mirror (SCIHUB_MIRROR_URLS) in turn until one works:
      1. POST /tabs -- open a tab navigated straight to {mirror}/{doi}.
         Sci-Hub mirrors have historically resolved a DOI appended directly
         to the domain, without needing the form at all.
      2. POST /tabs/:id/evaluate -- read the embedded PDF's `src` straight
         out of the DOM (see _PDF_SRC_SCRIPT) rather than guessing at a
         click target.
      3. If step 2 finds nothing, mirror this mirror's own reference form
         instead (exactly the manual flow: type the DOI into the "enter
         your reference" field, click "open"), then re-run step 2.
      4. Once a PDF src is found, fetch it directly via httpx -- once it's
         a raw file URL there's no more reason to route it back through
         the browser.
      5. DELETE /tabs/:id to clean up regardless of outcome, before moving
         to the next mirror if this one didn't produce a PDF.

    PLACEHOLDER caveats to verify against the deployed Camofox server's
    live /openapi.json or /docs once CAMOFOX_API_URL is wired up for real
    -- exact JSON field names (tab id, evaluate's result field, snapshot
    shape) are written from the README's documented examples, not a live
    response, and the reference-form element-matching heuristic
    (_find_ref_near) needs confirming against one real snapshot.

    Returns the PDF bytes, or None if no configured mirror worked.
    """
    if not settings.camofox_api_url or not settings.scihub_mirror_urls:
        return None

    base = settings.camofox_api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.camofox_access_key}"} if settings.camofox_access_key else {}
    mirrors = [m.strip().rstrip("/") for m in settings.scihub_mirror_urls.split(",") if m.strip()]

    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        for mirror in mirrors:
            pdf_bytes = await _camofox_try_mirror(client, base, doi, mirror)
            if pdf_bytes is not None:
                return pdf_bytes
    return None


async def _camofox_try_mirror(client: httpx.AsyncClient, base: str, doi: str, mirror: str) -> bytes | None:
    session_key = f"paper-{doi.replace('/', '_')}-{mirror.split('//')[-1].replace('.', '_')}"
    tab_id: str | None = None
    try:
        create_resp = await client.post(
            f"{base}/tabs",
            json={
                "userId": "ai-scientist-literature-agent",
                "sessionKey": session_key,
                "url": f"{mirror}/{doi}",
            },
        )
        create_resp.raise_for_status()
        tab_id = create_resp.json()["id"]  # PLACEHOLDER -- confirm response field name

        pdf_url = await _camofox_find_pdf_src(client, base, tab_id)
        if pdf_url is None:
            pdf_url = await _camofox_use_reference_form(client, base, tab_id, doi)
        if pdf_url is None:
            return None

        pdf_resp = await client.get(pdf_url if pdf_url.startswith("http") else f"https:{pdf_url}")
        pdf_resp.raise_for_status()
        if "pdf" not in pdf_resp.headers.get("content-type", ""):
            return None
        return pdf_resp.content
    except httpx.HTTPError:
        return None
    finally:
        if tab_id is not None:
            try:
                await client.delete(f"{base}/tabs/{tab_id}")
            except httpx.HTTPError:
                pass


async def _camofox_find_pdf_src(client: httpx.AsyncClient, base: str, tab_id: str) -> str | None:
    resp = await client.post(
        f"{base}/tabs/{tab_id}/evaluate",  # PLACEHOLDER -- confirm this endpoint's exact path/body shape
        json={"script": _PDF_SRC_SCRIPT},
    )
    resp.raise_for_status()
    return resp.json().get("result") or None  # PLACEHOLDER -- confirm response field name


async def _camofox_use_reference_form(client: httpx.AsyncClient, base: str, tab_id: str, doi: str) -> str | None:
    """Mirrors the manual sci-hub UI flow: type the DOI into the "enter
    your reference" input, click "open", then re-check for an embedded
    PDF. Used when navigating straight to {mirror}/{doi} didn't land on a
    PDF directly.
    """
    snapshot_resp = await client.get(f"{base}/tabs/{tab_id}/snapshot")
    snapshot_resp.raise_for_status()
    snapshot_text = snapshot_resp.json().get("snapshot", "")  # PLACEHOLDER -- confirm field name

    input_ref = _find_ref_near(snapshot_text, "reference")
    open_ref = _find_ref_near(snapshot_text, "open")
    if input_ref is None or open_ref is None:
        return None

    await client.post(f"{base}/tabs/{tab_id}/type", json={"ref": input_ref, "text": f"https://doi.org/{doi}"})
    await client.post(f"{base}/tabs/{tab_id}/click", json={"ref": open_ref})
    # PLACEHOLDER -- confirm POST /tabs/:id/wait's actual param shape;
    # this assumes a plain timeout wait for the new page to render.
    await client.post(f"{base}/tabs/{tab_id}/wait", json={"timeoutMs": 3000})

    return await _camofox_find_pdf_src(client, base, tab_id)


def _find_ref_near(snapshot_text: str, keyword: str) -> str | None:
    """Best-effort match of a clickable/typeable element ref (e.g. "e3")
    near given wording in a Camofox accessibility snapshot string.
    PLACEHOLDER heuristic -- confirm against a real snapshot's exact
    text/ref format.
    """
    import re

    match = re.search(rf"\[\w+ (e\d+)\][^\n]*\b{re.escape(keyword)}\b", snapshot_text, re.IGNORECASE)
    return match.group(1) if match else None


async def _download_one(doi: str, out_dir: Path, sem: asyncio.Semaphore) -> str:
    async with sem:
        pdf_bytes = await _try_sci_doc_hub(doi)
        source = "Sci-Doc-Hub"
        if pdf_bytes is None:
            pdf_bytes = await _try_camofox(doi)
            source = "Camofox"
        if pdf_bytes is None:
            pdf_bytes = await try_telegram_scihub_bot(doi)
            source = "Telegram Sci-Hub bot"

    if pdf_bytes is None:
        return f"- DOI {doi}: could not be downloaded (Sci-Doc-Hub, Camofox, and the Telegram Sci-Hub bot all failed)."

    out_path = out_dir / _doi_to_filename(doi)
    out_path.write_bytes(pdf_bytes)
    return f"- DOI {doi}: downloaded via {source} -> {out_path}"


@tool(
    "download_paper",
    "Given a list of DOIs (from one or more discover_papers/"
    "check_scihub_availability calls -- pass every DOI collected across a "
    "whole research query, not just one batch), download each paper's "
    "full-text PDF. Tries, per paper: (1) the Sci-Doc-Hub MCP server, (2) "
    "the Camofox stealth browser against configured Sci-Hub mirrors, (3) "
    "a Telegram Sci-Hub bot as a last resort. Downloads run concurrently "
    "(bounded) so many papers don't download one at a time. Saves each "
    "PDF into the shared project-local papers directory (same path for "
    "every user of this repo, not a personal folder) and returns each "
    "paper's path, or reports that no source could retrieve it.",
    {"dois": list},
)
async def download_paper(args: dict[str, Any]) -> dict[str, Any]:
    # De-duplicate while preserving order -- the same DOI can legitimately
    # show up across multiple discover_papers calls for one research query.
    seen: set[str] = set()
    dois = []
    for d in args["dois"]:
        doi = _strip_doi_prefix(d) if d else ""
        if doi and doi not in seen:
            seen.add(doi)
            dois.append(doi)

    if not dois:
        return {"content": [{"type": "text", "text": "No DOIs given to download."}]}

    # Project-local, gitignored (see data/README.md) -- resolved the same
    # way for every clone of this repo, not tied to any one person's
    # machine. Override via PAPERS_DOWNLOAD_DIR if you want it elsewhere.
    out_dir = Path(settings.papers_download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    lines = await asyncio.gather(*(_download_one(doi, out_dir, sem) for doi in dois))

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_literature_discovery_mcp_server():
    return create_sdk_mcp_server(
        name="literature_discovery",
        tools=[discover_papers, check_scihub_availability, download_paper],
    )
