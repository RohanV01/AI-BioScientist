"""Multi-stage research pipeline plan, ingestion stage: pulls real text out
of any URL a researcher pastes into their message, mirroring how
app/file_uploads.py handles an attached file. Deliberately generic-HTML-only
-- this module must NEVER call into app/tools/literature_discovery.py's
download_paper or the Camofox browser session it drives, which is the one
path in this codebase that can reach Sci-Hub. Keeping that reachability
structurally absent here (not just policy) is what lets every stage that
consumes ingested link content stay OA-only, per
docs/19-research-publication-readiness.md's rule that anything feeding a
benchmark/publication path must be OA-only.
"""
import hashlib
import logging
import re
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attachment

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://[^\s<>\"'()\[\]]+")
_TRAILING_PUNCTUATION = ".,;:!?"
_FETCH_TIMEOUT_SECONDS = 20


def extract_urls(text: str) -> list[str]:
    """Every http(s) URL in a raw Mattermost message, in the order they
    appear, deduped. Deliberately simple regex over exact string matching --
    Mattermost's own markdown/link-preview formatting is not something this
    needs to parse, just the literal URL a researcher pasted."""
    seen: set[str] = set()
    urls = []
    for match in _URL_PATTERN.findall(text):
        # A URL immediately followed by sentence punctuation in prose (a
        # trailing period, comma, etc.) shouldn't pull that punctuation in
        # as part of the URL -- strip it, since a real URL path component
        # ending in one of these is rare relative to "here's a link." prose.
        match = match.rstrip(_TRAILING_PUNCTUATION)
        if match and match not in seen:
            seen.add(match)
            urls.append(match)
    return urls


async def fetch_url_text(url: str) -> str | None:
    """Real HTTP GET + trafilatura content extraction -- generic web only,
    never a paper-mirror/Sci-Hub bypass. Returns None (never fabricates
    content) if the fetch fails or trafilatura finds nothing extractable
    (a login wall, a non-HTML response, a blocked request)."""
    import trafilatura  # imported lazily, same reasoning as llm_backend's per-backend lazy imports

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "OpenBioLab-research-agent/1.0"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch URL %s: %s", url, exc)
        return None

    extracted = trafilatura.extract(resp.text, include_comments=False, include_tables=True)
    return extracted.strip() if extracted else None


async def ingest_links(
    urls: list[str], experiment_dir: Path, db: AsyncSession, experiment_id, task_id=None,
) -> list[dict]:
    """Fetches every URL, writes a `<hash>.extracted.txt` sidecar (same
    convention app/file_uploads.py uses for uploaded documents) into
    <experiment_dir>/uploads/links/, and persists one Attachment row per
    URL. Returns [{url, status, path}] for the caller's own summary post."""
    links_dir = experiment_dir / "uploads" / "links"
    links_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for url in urls:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        dest_path = links_dir / f"{url_hash}.extracted.txt"
        text = await fetch_url_text(url)
        if text is None:
            results.append({"url": url, "status": "unreadable", "path": None})
            db.add(Attachment(
                experiment_id=experiment_id, task_id=task_id, source_type="url",
                original_ref=url, filename_or_title=url, detected_format="html",
                storage_path="", extraction_status="unreadable",
            ))
            continue

        dest_path.write_text(text)
        results.append({"url": url, "status": "ok", "path": str(dest_path)})
        db.add(Attachment(
            experiment_id=experiment_id, task_id=task_id, source_type="url",
            original_ref=url, filename_or_title=url, detected_format="html",
            storage_path=str(dest_path), extraction_status="ok",
        ))

    return results
