"""
Phase 2.7 — Tissue expression & safety.

PRD wants GTEx + HPA with `tissue_of_interest` as the default query tissue and a
critical-tissue flag (heart/brain/kidney TPM > 10 → require a selectivity
strategy). The local GTEx parquet is sample-level (no tissue annotations shipped),
so HPA's per-gene RNA tissue specificity is the primary source here; it gives both
the specificity category and the enriched-tissue nTPM values we need.

Outputs:
  tissue_specificity   HPA category string
  tsi                  0–1 specificity index (higher = more restricted = safer)
  critical_tissue_flag high expression in heart / brain / kidney
  broadly_expressed    "detected in all/many" with low specificity
  toi_expressed        whether the run's tissue_of_interest shows expression
"""
from __future__ import annotations
import logging
import re
from typing import Dict, Optional

from .hpa import get_hpa

log = logging.getLogger(__name__)

_TSI_BY_CATEGORY = {
    "tissue enriched": 0.9,
    "group enriched": 0.75,
    "tissue enhanced": 0.6,
    "low tissue specificity": 0.2,
    "not detected": 0.0,
}

_CRITICAL_TISSUES = ("heart", "brain", "cerebral", "cortex", "kidney", "renal",
                     "cardiac", "myocard")
_CRITICAL_TPM = 10.0


def get_expression_safety(symbol: str, ensembl_id: str, tissue_of_interest: str) -> Dict:
    empty = {
        "tissue_specificity": "unknown", "tsi": 0.5,
        "critical_tissue_flag": False, "broadly_expressed": False,
        "toi_expressed": None, "specific_tissues": {}, "source": "none",
    }
    hpa = get_hpa(ensembl_id)
    if not hpa:
        log.warning("[2.7] %s: no HPA expression record", symbol)
        return empty

    category = hpa.get("RNA tissue specificity", "").strip()
    distribution = hpa.get("RNA tissue distribution", "").strip().lower()
    specific = _parse_tissue_ntpm(hpa.get("RNA tissue specific nTPM", ""))

    tsi = _TSI_BY_CATEGORY.get(category.lower(), 0.5)
    broadly = (("detected in all" in distribution or "detected in many" in distribution)
               and tsi <= 0.2)

    # Critical-tissue flag from enriched nTPM list.
    critical = any(
        any(ct in tissue.lower() for ct in _CRITICAL_TISSUES) and tpm > _CRITICAL_TPM
        for tissue, tpm in specific.items()
    )
    # Broad expression in a gene we can't restrict → conservatively treat criticals
    # as a possible safety concern even when not in the enriched list.
    if broadly:
        critical = True

    toi = None
    if tissue_of_interest:
        toi = any(tissue_of_interest.lower() in t.lower() for t in specific) or broadly

    log.info("[2.7] %s: %s (tsi=%.2f, critical=%s)", symbol, category or "n/a", tsi, critical)
    return {
        "tissue_specificity": category or "unknown",
        "tsi": round(tsi, 3),
        "critical_tissue_flag": critical,
        "broadly_expressed": broadly,
        "toi_expressed": toi,
        "specific_tissues": specific,
        "source": "hpa",
    }


def _parse_tissue_ntpm(raw: str) -> Dict[str, float]:
    """Parse 'bone marrow: 49.9;lymphoid tissue: 70.9' → {tissue: tpm}."""
    out: Dict[str, float] = {}
    for chunk in raw.split(";"):
        if ":" not in chunk:
            continue
        name, _, val = chunk.rpartition(":")
        m = re.search(r"[-+]?\d*\.?\d+", val)
        if name.strip() and m:
            out[name.strip()] = float(m.group())
    return out
