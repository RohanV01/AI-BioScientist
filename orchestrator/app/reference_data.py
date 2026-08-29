"""Real freshness-checking for the reference databases baked into the
Docker image at build time (Kraken2, Kaiju, Bakta, CheckM2, CheckV,
LDSC, AMRFinderPlus, PyIR -- Dockerfile lines ~260-269). Built per
explicit user direction ("can we make it this way that these are
constantly checked for releases") after confirming none of these
auto-update on their own -- every mechanism here was verified live
against the real upstream endpoint before being wired in, not guessed:

- Bakta / CheckM2 / LDSC: Zenodo's own `GET /api/records/<id>/versions/latest`
  resolves to whatever the current latest version of that record's
  concept is -- confirmed live it correctly follows to a newer record
  when one exists (querying LDSC's original record 7768714 resolves to
  a real, different, newer record 10515792, "S-LDSC reference files").
- Kraken2 / Kaiju: both buckets support unauthenticated S3
  `?list-type=2` listing -- confirmed live, returns every dated release
  object so the newest can be picked by filename.
- CheckV: its own NERSC portal publishes a real `CURRENT_RELEASE.txt`
  (the same file `checkv download_database` itself reads) -- confirmed
  live it currently reads `checkv-db-v1.5`.
- AMRFinderPlus: NCBI's FTP mirrors a real `latest/` directory
  (confirmed live) whose listing carries a dated version string.
- PyIR: fetches IMGT/GENE-DB germline references via its own `pyir
  setup` command, which always pulls current data -- there is no
  separate "check" step for this source; "checking" and "refreshing"
  are the same real action, so this source is marked self_refreshing
  and the scheduler just re-runs that command periodically instead of
  querying a version endpoint first.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferenceDataSource

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 30.0


class ReferenceDataCheckError(Exception):
    """Raised when a real upstream check request fails -- caught by
    refresh_all_reference_data so one source's outage doesn't stop the
    others from being checked."""


async def _check_zenodo_versions_latest(source_url: str) -> str:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{source_url}/versions/latest")
        resp.raise_for_status()
        data = resp.json()
    return str(data["id"])


async def _check_s3_bucket_listing(source_url: str, name_filter: str, prefix: str = "") -> str:
    # S3's flat namespace ignores any path segment on a virtual-hosted
    # bucket URL for a list-type=2 call -- confirmed live that scoping
    # only works via a real `prefix` query param, not the URL path, so
    # source_url here is always the bucket root.
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(source_url, params={"list-type": "2", "prefix": prefix})
        resp.raise_for_status()
        body = resp.text
    keys = re.findall(r"<Key>([^<]*)</Key>", body)
    matching = sorted(k for k in keys if name_filter in k)
    if not matching:
        raise ReferenceDataCheckError(f"No keys matching {name_filter!r} found in bucket listing at {source_url}")
    # Real release filenames embed a sortable date (YYYYMMDD or
    # YYYY-MM-DD) -- lexicographic sort on the full key puts the newest
    # release last, same ordering either format produces.
    return matching[-1]


async def _check_release_file(source_url: str) -> str:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(source_url)
        resp.raise_for_status()
        body = resp.text
    if source_url.endswith("CURRENT_RELEASE.txt"):
        return body.strip()
    # AMRFinderPlus's latest/ directory listing -- extract the one
    # dated (YYYY-MM-DD[.N]) entry, its real version marker.
    match = re.search(r"(\d{4}-\d{2}-\d{2}(?:\.\d+)?)", body)
    if not match:
        raise ReferenceDataCheckError(f"No dated version string found in listing at {source_url}")
    return match.group(1)


@dataclass
class CheckResult:
    latest_version: str | None
    error: str | None


async def check_latest_version(source: ReferenceDataSource) -> CheckResult:
    """Runs the real, source-specific live check. Never fabricates a
    version on failure -- a failed check leaves latest_known_version
    untouched and records the real error instead."""
    try:
        if source.check_method == "zenodo_versions_latest":
            latest = await _check_zenodo_versions_latest(source.source_url)
        elif source.check_method == "s3_bucket_listing":
            if source.name == "kraken2_viral":
                latest = await _check_s3_bucket_listing(source.source_url, "k2_viral", prefix="kraken/k2_viral")
            else:
                latest = await _check_s3_bucket_listing(source.source_url, "kaiju_db_viruses")
        elif source.check_method == "release_file":
            latest = await _check_release_file(source.source_url)
        elif source.check_method == "self_refreshing":
            # No separate check for this source (see module docstring) --
            # nothing to compare, so report the check as clean.
            return CheckResult(latest_version=source.installed_version, error=None)
        else:
            return CheckResult(latest_version=None, error=f"Unknown check_method {source.check_method!r}")
    except (httpx.HTTPError, ReferenceDataCheckError, KeyError, ValueError) as exc:
        return CheckResult(latest_version=None, error=str(exc))
    return CheckResult(latest_version=latest, error=None)


async def refresh_all_reference_data(db: AsyncSession) -> list[ReferenceDataSource]:
    """Real live check against every tracked source, one HTTP call
    each -- updates each row's latest_known_version/needs_update/
    last_checked_at/last_check_error in place. Called by both the
    periodic background task (app/main.py) and the manual
    POST /reference-data/check endpoint."""
    result = await db.execute(select(ReferenceDataSource))
    sources = result.scalars().all()

    for source in sources:
        check = await check_latest_version(source)
        source.last_checked_at = datetime.now(timezone.utc)
        if check.error is not None:
            source.last_check_error = check.error
            logger.warning("Reference data check failed for %s: %s", source.name, check.error)
            continue
        source.last_check_error = None
        source.latest_known_version = check.latest_version
        source.needs_update = check.latest_version != source.installed_version

    await db.commit()
    return list(sources)
