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

A third tool, download_paper, does the actual full-text PDF acquisition:
given DOIs from the two tools above, it drives the Camofox stealth
browser through the real Sci-Hub UI (paste DOI, open, click save) and
saves each resulting PDF to the shared project-local papers directory.
"""
import asyncio
import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pymupdf

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.config import settings
from app.experiment_context import findings_dir, load_manifest, papers_dir, update_manifest_entry
from app.llm_backend import LLMBackendError
from app.llm_backend import complete as llm_complete

OPENALEX_URL = "https://api.openalex.org/works"


def _strip_doi_prefix(doi: str) -> str:
    return doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()


async def _openalex_get(client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
    """GET against OPENALEX_URL with one retry on 429 -- OpenAlex's
    anonymous-pool rate limit kicks in under load and self-clears within
    its own advertised `retryAfter` window (seen in practice: ~30s), so a
    single wait-and-retry turns a transient rate limit into a real result
    instead of a tool failure. Any other status is left to the caller's
    own resp.raise_for_status()."""
    resp = await client.get(OPENALEX_URL, params=params)
    if resp.status_code == 429:
        retry_after = min(float(resp.json().get("retryAfter", 5)), 30.0)
        await asyncio.sleep(retry_after)
        resp = await client.get(OPENALEX_URL, params=params)
    return resp


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
        resp = await _openalex_get(
            client,
            {
                "search": args["query"],
                "per_page": max_results,
                # relevance_score/cited_by_count are real OpenAlex fields
                # this was already paying for but not surfacing -- the
                # selection-gate policy (system prompt) needs real signal to
                # rank against instead of guessing from titles alone.
                "select": "doi,title,publication_year,open_access,primary_topic,relevance_score,cited_by_count",
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
        title = r.get("title", "")
        year = r.get("publication_year", "")
        relevance = r.get("relevance_score")
        cited_by = r.get("cited_by_count", 0)
        lines.append(
            f"- DOI {doi}: {title} ({year}, {subfield}) -- {oa_bit} "
            f"[relevance {relevance:.1f}, cited by {cited_by}]"
            if relevance is not None
            else f"- DOI {doi}: {title} ({year}, {subfield}) -- {oa_bit} [cited by {cited_by}]"
        )
        # Cross-cutting paper-selection gate (see the Experiments plan): every
        # DOI this tool ever surfaces gets a manifest entry, so a later
        # download_paper/read_paper call in the same experiment can dedup
        # against it instead of re-fetching. No-op if no experiment is in
        # scope (see app/experiment_context.py).
        update_manifest_entry(
            doi, title=title, is_oa=bool(oa.get("is_oa")), relevance_score=relevance,
            cited_by_count=cited_by, status="discovered",
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
        resp = await _openalex_get(
            client,
            {"filter": "doi:" + "|".join(dois), "select": "doi,open_access", "per_page": len(dois)},
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
# one download_paper call) doesn't hammer Camofox with dozens of
# simultaneous tab sessions at once.
_DOWNLOAD_CONCURRENCY = 5


def _doi_to_filename(doi: str) -> str:
    return doi.replace("/", "_") + ".pdf"


# Live-verified (2026-08-22) against sci-hub.ren + Sci-Doc-Hub's own PDF
# host (sci.bban.top): every landing page renders a "save" button (an
# accessible <button> in the TOP-LEVEL page, not buried inside the
# embedded PDF viewer) that triggers a genuine browser download when
# clicked -- Camofox's Playwright download listener captures it
# automatically (see external/camofox-browser/lib/downloads.js). This is
# the same click a human would make, so it goes through the real browser
# network stack: no bare-httpx GET (hits the host's 403 anti-bot check,
# which the user said to leave unfixed) and no in-page fetch() (hits
# CORS, since the PDF host doesn't send Access-Control-Allow-Origin for
# sci-hub.ren's origin).
_SAVE_BUTTON_RE = re.compile(r'button "([^"]*\b(?:save|download)\b[^"]*)" \[(e\d+)\]', re.IGNORECASE)
_REF_INPUT_RE = re.compile(r'textbox "[^"]*reference[^"]*" \[(e\d+)\]', re.IGNORECASE)
_OPEN_BUTTON_RE = re.compile(r'button "open"[^\n]*\[(e\d+)\]', re.IGNORECASE)


async def _try_camofox(doi: str) -> bytes | None:
    """The full-text acquisition source for download_paper: Camofox
    stealth headless browser
    (https://github.com/jo-inc/camofox-browser --
    Vault/AI-Tools/camofox-browser-stealth-headless-browser-2026-08-16.md).

    Drives the exact manual flow a human uses on sci-hub.ren: open the
    site (or navigate straight to {mirror}/{doi}, which lands on the same
    result page directly), click the page's own "save" button, then poll
    Camofox's captured-downloads list for the resulting file. Tries each
    configured Sci-Hub mirror (SCIHUB_MIRROR_URLS) in turn until one
    produces a real PDF.

    Field names verified against a real local clone's server.js/openapi.json
    (external/camofox-browser, 2026-08-20) and against a live end-to-end run
    against sci-hub.ren (2026-08-22, see session notes): POST /tabs body
    {userId, sessionKey, url} -> {tabId, url}; GET /tabs/:id/snapshot ->
    {snapshot}; POST /tabs/:id/{type,click,wait}; GET
    /tabs/:id/downloads?userId=...&includeData=true -> {downloads: [{id,
    mimeType, bytes, dataBase64, failure, ...}]}; DELETE /tabs/:id.

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


_CAMOFOX_USER_ID = "ai-scientist-literature-agent"
_DOWNLOAD_POLL_ATTEMPTS = 6
_DOWNLOAD_POLL_INTERVAL_S = 1.0


async def _camofox_try_mirror(client: httpx.AsyncClient, base: str, doi: str, mirror: str) -> bytes | None:
    session_key = f"paper-{doi.replace('/', '_')}-{mirror.split('//')[-1].replace('.', '_')}"
    tab_id: str | None = None
    try:
        create_resp = await client.post(
            f"{base}/tabs",
            json={"userId": _CAMOFOX_USER_ID, "sessionKey": session_key, "url": f"{mirror}/{doi}"},
        )
        create_resp.raise_for_status()
        tab_id = create_resp.json()["tabId"]

        pdf_bytes = await _camofox_click_save_and_capture(client, base, tab_id)
        if pdf_bytes is None:
            # Direct {mirror}/{doi} didn't render a result page with a
            # save button -- fall back to the manual form flow (type the
            # DOI into "enter your reference", click "open") and retry.
            if await _camofox_use_reference_form(client, base, tab_id, doi):
                pdf_bytes = await _camofox_click_save_and_capture(client, base, tab_id)
        return pdf_bytes
    except httpx.HTTPError:
        return None
    finally:
        if tab_id is not None:
            try:
                await client.delete(f"{base}/tabs/{tab_id}", params={"userId": _CAMOFOX_USER_ID})
            except httpx.HTTPError:
                pass


async def _camofox_click_save_and_capture(client: httpx.AsyncClient, base: str, tab_id: str) -> bytes | None:
    snapshot_resp = await client.get(f"{base}/tabs/{tab_id}/snapshot", params={"userId": _CAMOFOX_USER_ID})
    snapshot_resp.raise_for_status()
    snapshot_text = snapshot_resp.json().get("snapshot", "")

    match = _SAVE_BUTTON_RE.search(snapshot_text)
    if match is None:
        return None
    save_ref = match.group(2)

    await client.post(f"{base}/tabs/{tab_id}/click", json={"userId": _CAMOFOX_USER_ID, "ref": save_ref})

    for _ in range(_DOWNLOAD_POLL_ATTEMPTS):
        await asyncio.sleep(_DOWNLOAD_POLL_INTERVAL_S)
        downloads_resp = await client.get(
            f"{base}/tabs/{tab_id}/downloads", params={"userId": _CAMOFOX_USER_ID, "includeData": "true"}
        )
        downloads_resp.raise_for_status()
        downloads = downloads_resp.json().get("downloads", [])
        if not downloads:
            continue
        entry = downloads[-1]
        if entry.get("failure"):
            return None
        data_b64 = entry.get("dataBase64")
        if data_b64:
            return base64.b64decode(data_b64)
    return None


async def _camofox_use_reference_form(client: httpx.AsyncClient, base: str, tab_id: str, doi: str) -> bool:
    """Mirrors the manual sci-hub UI flow: type the DOI into the "enter
    your reference" input, click "open". Used when navigating straight to
    {mirror}/{doi} didn't land on a result page with a save button.
    Returns whether the form was found and submitted.
    """
    snapshot_resp = await client.get(f"{base}/tabs/{tab_id}/snapshot", params={"userId": _CAMOFOX_USER_ID})
    snapshot_resp.raise_for_status()
    snapshot_text = snapshot_resp.json().get("snapshot", "")

    input_match = _REF_INPUT_RE.search(snapshot_text)
    open_match = _OPEN_BUTTON_RE.search(snapshot_text)
    if input_match is None or open_match is None:
        return False
    input_ref, open_ref = input_match.group(1), open_match.group(1)

    await client.post(
        f"{base}/tabs/{tab_id}/type",
        json={"userId": _CAMOFOX_USER_ID, "ref": input_ref, "text": f"https://doi.org/{doi}", "submit": False},
    )
    await client.post(f"{base}/tabs/{tab_id}/click", json={"userId": _CAMOFOX_USER_ID, "ref": open_ref})
    await client.post(f"{base}/tabs/{tab_id}/wait", json={"userId": _CAMOFOX_USER_ID, "timeout": 3000})
    return True


# Content-integrity check: live testing this session found a real case
# where Camofox successfully downloaded a real PDF via a real browser
# download, with no error anywhere in the pipeline, but the PDF's actual
# content was a completely unrelated paper (a bad Sci-Hub mirror response
# for that specific DOI) -- nothing before this point can catch that, since
# every step up to here genuinely succeeded. Two cheap signals, no extra
# API cost when a title's already cached from a prior discover_papers call:
# (1) does the paper's own DOI appear printed in its first page(s), and
# (2) does a majority of the expected title's distinctive words appear
# there. Either passing counts as verified.
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "with",
    "from", "by", "at", "is", "as", "this", "that", "its", "into", "via",
}
_CONTENT_CHECK_HEAD_CHARS = 5000


def _significant_words(title: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


async def _expected_title(doi: str) -> str | None:
    # Free if discover_papers already surfaced this DOI in the current
    # experiment (app/experiment_context.py's manifest) -- only falls back
    # to a live OpenAlex lookup when download_paper was called for a DOI
    # nothing discovered first (e.g. via check_scihub_availability alone).
    cached = load_manifest().get(doi, {}).get("title")
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await _openalex_get(
                client, {"filter": f"doi:{doi}", "select": "title", "per_page": 1}
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0].get("title") if results else None
        except httpx.HTTPError:
            return None


async def _verify_pdf_content(pdf_path: Path, doi: str) -> tuple[bool, str]:
    """Returns (verified, reason). "Can't check" (no title available, e.g.
    OpenAlex has no record for this DOI) counts as verified rather than a
    false-positive mismatch -- this is a fraud/mistake detector, not a
    requirement every legitimate DOI can satisfy.
    """
    text = await asyncio.to_thread(_extract_pdf_text, pdf_path)
    head = text[:_CONTENT_CHECK_HEAD_CHARS].lower()

    if doi.lower() in head:
        return True, "the paper's own DOI appears printed in its text"

    title = await _expected_title(doi)
    if not title:
        return True, "no title available to check against (OpenAlex has no record for this DOI)"

    expected_words = _significant_words(title)
    if not expected_words:
        return True, "title had no distinctive words to check against"

    matched = sum(1 for w in expected_words if w in head)
    overlap = matched / len(expected_words)
    if overlap >= 0.5:
        return True, f"{overlap:.0%} of the expected title's distinctive words found in the PDF"
    return False, (
        f"only {overlap:.0%} of the expected title's distinctive words appear in the PDF's "
        "text -- this downloaded file may not actually be the requested paper"
    )


async def _download_one(doi: str, out_dir: Path, sem: asyncio.Semaphore) -> str:
    # Paper-selection dedup gate (Experiments plan): if this DOI's PDF is
    # already on disk for the current experiment, don't re-hit Camofox for
    # it -- a second, overlapping discover_papers call later in the same
    # experiment shouldn't pay the same download cost twice.
    out_path = out_dir / _doi_to_filename(doi)
    if out_path.is_file():
        return f"- DOI {doi}: already downloaded -> {out_path}"

    # Isolated per-DOI rather than letting an unexpected exception
    # propagate up into the batch's asyncio.gather -- a bug/edge-case on
    # one DOI's Camofox call must not cancel every other DOI's in-flight
    # download (bit us for real when Tier 3/Telegram was still in the
    # waterfall: an unhandled RPCError on one DOI silently dropped an
    # already-successful download for a different DOI in the same batch,
    # since gather() re-raises on the first exception without waiting for
    # the rest).
    try:
        async with sem:
            pdf_bytes = await _try_camofox(doi)
            source = "Camofox"
    except Exception as exc:
        return f"- DOI {doi}: download failed with an unexpected error ({exc})."

    if pdf_bytes is None:
        update_manifest_entry(doi, status="skipped")
        return f"- DOI {doi}: could not be downloaded (Camofox failed to retrieve a PDF for this DOI)."

    out_path.write_bytes(pdf_bytes)

    verified, reason = await _verify_pdf_content(out_path, doi)
    update_manifest_entry(doi, status="downloaded", content_verified=verified, content_check=reason)
    if not verified:
        return (
            f"- DOI {doi}: downloaded via {source} -> {out_path} -- "
            f"⚠️ CONTENT MISMATCH WARNING: {reason}. Do not cite this file's "
            f"content for DOI {doi} without manually confirming it's correct."
        )
    return f"- DOI {doi}: downloaded via {source} -> {out_path}"


@tool(
    "download_paper",
    "Given a list of DOIs (from one or more discover_papers/"
    "check_scihub_availability calls -- pass every DOI collected across a "
    "whole research query, not just one batch), download each paper's "
    "full-text PDF via the Camofox stealth browser against configured "
    "Sci-Hub mirrors (drives the real UI: paste the DOI, click open, "
    "click the page's own save button, capture the resulting browser "
    "download). Downloads run concurrently (bounded) so many papers don't "
    "download one at a time. Saves each PDF into the current experiment's "
    "own papers folder and returns each paper's path, or reports that it "
    "could not be retrieved. Already-downloaded DOIs are skipped, not "
    "re-fetched.",
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

    # Experiment-scoped folder when an agent run is in progress
    # (app/experiment_context.py); falls back to the old shared
    # project-local dir for standalone/test invocations with no experiment
    # in scope. Gitignored either way (see data/README.md).
    out_dir = papers_dir() or Path(settings.papers_download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    lines = await asyncio.gather(*(_download_one(doi, out_dir, sem) for doi in dois))

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# Cap on how much extracted PDF text goes into the structured-extraction
# prompt -- most papers fit comfortably; this just bounds the worst case
# (a huge PDF) rather than sending an unbounded amount of text per call.
_MAX_EXTRACTION_CHARS = 60_000

_EXTRACTION_PROMPT = """\
Extract structured findings from this scientific paper's full text for a \
research database. Return ONLY a JSON object (no markdown fences, no \
commentary before or after) with exactly this shape:

{{
  "claims": [{{"claim": "...", "support": "a specific quote or section reference from the text below"}}],
  "methods_summary": "...",
  "key_results": "...",
  "limitations": "..."
}}

Every claim's "support" must point to something that actually appears in \
the text below -- never invent a finding, quote, or number that isn't \
there. If the text is truncated or a section is unclear, say so in that \
field rather than guessing.

Paper text:
{text}
"""


def _doi_to_finding_filename(doi: str) -> str:
    return doi.replace("/", "_") + ".json"


def _extract_pdf_text(pdf_path: Path) -> str:
    doc = pymupdf.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _parse_extraction_response(raw: str) -> dict:
    # The prompt asks for bare JSON, but strip markdown fences defensively
    # in case the model wraps it anyway.
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


async def _extract_structured_findings(pdf_text: str) -> dict:
    raw = await llm_complete(
        _EXTRACTION_PROMPT.format(text=pdf_text[:_MAX_EXTRACTION_CHARS]), max_tokens=2000
    )
    return _parse_extraction_response(raw)


def _format_findings_for_agent(doi: str, findings: dict) -> str:
    lines = [f"Structured findings for DOI {doi} (extracted from the downloaded PDF):"]
    for c in findings.get("claims", []):
        lines.append(f"- Claim: {c.get('claim', '')}\n  Support: {c.get('support', '')}")
    if findings.get("methods_summary"):
        lines.append(f"Methods: {findings['methods_summary']}")
    if findings.get("key_results"):
        lines.append(f"Key results: {findings['key_results']}")
    if findings.get("limitations"):
        lines.append(f"Limitations: {findings['limitations']}")
    return "\n".join(lines)


@tool(
    "read_paper",
    "Given a DOI already downloaded via download_paper, extract its actual "
    "content -- claims (each with a supporting quote/reference), a methods "
    "summary, key results, and limitations -- so you can cite what a paper "
    "genuinely says instead of guessing from its title. Persists the "
    "structured findings into the current experiment's findings folder; "
    "calling this again for the same DOI in the same experiment returns "
    "the cached result instead of re-extracting.",
    {"doi": str},
)
async def read_paper(args: dict[str, Any]) -> dict[str, Any]:
    doi = _strip_doi_prefix(args["doi"])

    pdir = papers_dir()
    if pdir is None:
        return {
            "content": [{
                "type": "text",
                "text": "No experiment is currently in scope -- read_paper needs a PDF "
                        "downloaded via download_paper within a live experiment.",
            }]
        }

    pdf_path = pdir / _doi_to_filename(doi)
    if not pdf_path.is_file():
        return {"content": [{"type": "text", "text": f"No downloaded PDF found for DOI {doi} -- call download_paper first."}]}

    # download_paper's content-integrity check (see _verify_pdf_content)
    # flagged this file as a possible mismatch -- refuse to extract
    # "findings" from a paper that may not actually be this DOI at all.
    manifest_entry = load_manifest().get(doi, {})
    if manifest_entry.get("content_verified") is False:
        return {
            "content": [{
                "type": "text",
                "text": f"Refusing to extract findings for DOI {doi}: download_paper flagged this "
                        f"file's content as a possible mismatch ({manifest_entry.get('content_check', 'unknown reason')}). "
                        "Re-download from a different mirror and confirm before reading.",
            }]
        }

    fdir = findings_dir()
    finding_path = fdir / _doi_to_finding_filename(doi)

    # Dedup gate (Experiments plan): a DOI already read in this experiment
    # doesn't get re-extracted -- that's a real Anthropic API call per DOI,
    # not free.
    if finding_path.is_file():
        cached = json.loads(finding_path.read_text())
        return {"content": [{"type": "text", "text": _format_findings_for_agent(doi, cached) + "\n(cached)"}]}

    pdf_text = await asyncio.to_thread(_extract_pdf_text, pdf_path)
    if not pdf_text.strip():
        return {"content": [{"type": "text", "text": f"PDF for DOI {doi} contained no extractable text (scanned image, not real text)."}]}

    try:
        findings = await _extract_structured_findings(pdf_text)
    except (LLMBackendError, json.JSONDecodeError) as exc:
        return {"content": [{"type": "text", "text": f"Structured extraction failed for DOI {doi}: {exc}"}]}

    # Stamp the DOI into the persisted record itself -- the filename alone
    # isn't a safe round-trip for a DOI containing more than one "/", and
    # Phase 3's conclusion synthesis reads every findings/*.json without
    # needing to un-mangle filenames.
    findings["doi"] = doi
    fdir.mkdir(parents=True, exist_ok=True)
    finding_path.write_text(json.dumps(findings, indent=2))
    update_manifest_entry(doi, status="read")

    return {"content": [{"type": "text", "text": _format_findings_for_agent(doi, findings)}]}


def build_literature_discovery_mcp_server():
    return create_sdk_mcp_server(
        name="literature_discovery",
        tools=[discover_papers, check_scihub_availability, download_paper, read_paper],
    )
