"""
Shared Human Protein Atlas per-gene loader.

HPA publishes one TSV per gene at https://www.proteinatlas.org/{ENSG}.tsv with a
single data row covering subcellular location, protein class, secretome, and RNA
tissue specificity. We cache each download into Databases/human_protein_atlas/
single_gene_entries/{ENSG}.tsv (the repo already ships one such file) so repeat
runs and offline use hit local disk first.

Both localization.py (2.6 routing) and expression.py (2.7 safety) consume this.
"""
from __future__ import annotations
import csv
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import httpx

from src.config import settings

log = logging.getLogger(__name__)

_HPA_TSV_URL = "https://www.proteinatlas.org/{ensembl}.tsv"


def _entries_dir() -> Path:
    d = settings.DB_HPA / "single_gene_entries"
    d.mkdir(parents=True, exist_ok=True)
    return d


@lru_cache(maxsize=512)
def get_hpa(ensembl_id: str) -> Optional[Dict[str, str]]:
    """
    Return the HPA row for an Ensembl gene id as a {column: value} dict, or None.
    Local cache first, then REST download.
    """
    if not ensembl_id:
        return None
    # Ensembl ids in HPA files are version-stripped (ENSG00000134057)
    ensg = ensembl_id.split(".")[0]

    cached = _entries_dir() / f"{ensg}.tsv"
    if cached.exists():
        row = _parse_tsv(cached)
        if row:
            return row

    text = _download(ensg)
    if not text:
        return None
    try:
        cached.write_text(text)
    except OSError:
        pass
    return _parse_row_text(text)


def _download(ensg: str, retries: int = 2) -> Optional[str]:
    for attempt in range(retries):
        try:
            resp = httpx.get(_HPA_TSV_URL.format(ensembl=ensg), timeout=30,
                             follow_redirects=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.debug("[HPA] download %s failed (%d): %s", ensg, attempt + 1, exc)
    return None


def _parse_tsv(path: Path) -> Optional[Dict[str, str]]:
    try:
        return _parse_row_text(path.read_text())
    except OSError:
        return None


def _parse_row_text(text: str) -> Optional[Dict[str, str]]:
    reader = csv.reader(text.splitlines(), delimiter="\t", quotechar='"')
    rows = list(reader)
    if len(rows) < 2:
        return None
    header, data = rows[0], rows[1]
    return {h: (data[i] if i < len(data) else "") for i, h in enumerate(header)}
