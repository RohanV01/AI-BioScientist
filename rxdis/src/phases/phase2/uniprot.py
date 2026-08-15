"""
Gene symbol → UniProt accession resolution + lightweight gene metadata.

Needed by:
  - structure.py   (AlphaFold DB / PDB are keyed by UniProt)
  - variants.py    (AlphaMissense is keyed by UniProt)
  - chembl.py      (target lookup via component_sequences.accession)

Primary source: UniProt REST (reviewed/Swiss-Prot, human). Results are cached in
a module-level dict for the lifetime of a run (callers loop over ~20 targets).
"""
from __future__ import annotations
import logging
import time
from typing import Dict, Optional

import httpx

log = logging.getLogger(__name__)

_UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"

# symbol -> {uniprot, length, sequence, recommended_name, keywords[]}
_CACHE: Dict[str, Optional[dict]] = {}


def resolve_uniprot(symbol: str, ensembl_id: str = "") -> Optional[dict]:
    """
    Resolve a HGNC gene symbol to its reviewed human UniProt entry.
    Returns {uniprot, length, sequence, recommended_name, keywords} or None.
    """
    if symbol in _CACHE:
        return _CACHE[symbol]

    entry = _query_uniprot(f'(gene_exact:{symbol}) AND (organism_id:9606) AND (reviewed:true)')
    if entry is None and ensembl_id:
        # Fall back to cross-reference lookup by Ensembl gene id
        entry = _query_uniprot(f'(xref:ensembl-{ensembl_id}) AND (organism_id:9606) AND (reviewed:true)')
    if entry is None:
        # Last resort: unreviewed (TrEMBL) — common for poorly studied / Tdark genes
        entry = _query_uniprot(f'(gene_exact:{symbol}) AND (organism_id:9606)')

    _CACHE[symbol] = entry
    if entry:
        log.info("[2.x] %s → UniProt %s (%d aa)", symbol, entry["uniprot"], entry.get("length", 0))
    else:
        log.warning("[2.x] No UniProt entry for %s", symbol)
    return entry


def _query_uniprot(query: str, retries: int = 3) -> Optional[dict]:
    params = {
        "query": query,
        "format": "json",
        "size": 1,
        "fields": "accession,length,sequence,protein_name,keyword",
    }
    for attempt in range(retries):
        try:
            resp = httpx.get(_UNIPROT_SEARCH, params=params, timeout=30)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None
            r = results[0]
            name = ""
            try:
                name = r["proteinDescription"]["recommendedName"]["fullName"]["value"]
            except (KeyError, TypeError):
                pass
            return {
                "uniprot": r["primaryAccession"],
                "length": r.get("sequence", {}).get("length", 0),
                "sequence": r.get("sequence", {}).get("value", ""),
                "recommended_name": name,
                "keywords": [k.get("name", "") for k in r.get("keywords", [])],
            }
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            log.warning("[2.x] UniProt query failed (attempt %d/%d): %s", attempt + 1, retries, exc)
            time.sleep(2 ** attempt)
    return None
