"""
Phase 2.1 — Essentiality from DepMap CRISPR (Chronos) gene-effect scores.

DepMap `CRISPRGeneEffect.csv`: rows = cell lines, columns = "SYMBOL (ENTREZ)".
A Chronos score near 0 means no effect; strongly negative (≈ -1) means the gene
is essential in that line. We summarise per gene across all lines:

  chronos_median        median effect across all cell lines
  is_core_essential     pan-essential (median < -1.0 and broadly negative)
  selective_fraction    fraction of lines with score < -0.5 (selective dependency)

PRD `indication_type` interaction:
  - core-essential + non-oncology → high-tox flag (handled in scoring.py, -25%).
  - oncology prefers *selective* essentiality over pan-essential.

For non-oncology genes silent in DepMap, the PRD routes to ProteomeLM-Ess via
Modal. That is gated behind MODAL_TOKEN; when absent we return is_in_depmap=False
and let scoring.py treat essentiality as unknown (neutral).
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.config import settings

log = logging.getLogger(__name__)

_CORE_ESSENTIAL_MEDIAN = -1.0
_DEPENDENCY_THRESHOLD = -0.5


@lru_cache(maxsize=1)
def _column_index() -> Dict[str, str]:
    """
    Map gene symbol → exact column header ("SYMBOL (ENTREZ)") by reading only
    the header row of the CSV (cheap — does not load the 440MB body).
    """
    path = settings.DB_DEPMAP / "CRISPRGeneEffect.csv"
    if not path.exists():
        log.warning("[2.1] DepMap file not found at %s", path)
        return {}
    header = pd.read_csv(path, nrows=0)
    mapping: Dict[str, str] = {}
    for col in header.columns:
        sym = col.split(" (")[0].strip()
        if sym:
            mapping[sym] = col
    log.info("[2.1] DepMap header indexed: %d genes", len(mapping))
    return mapping


def get_essentiality(symbol: str) -> Dict:
    """
    Return essentiality summary for one gene.
    {chronos_median, is_core_essential, selective_fraction, is_in_depmap, n_lines}
    """
    col_map = _column_index()
    col = col_map.get(symbol)
    if col is None:
        return {
            "chronos_median": None,
            "is_core_essential": False,
            "selective_fraction": 0.0,
            "is_in_depmap": False,
            "n_lines": 0,
        }

    path = settings.DB_DEPMAP / "CRISPRGeneEffect.csv"
    try:
        # Read only the single gene column (plus implicit index) — fast.
        series = pd.read_csv(path, usecols=[col])[col].dropna()
    except Exception as exc:
        log.warning("[2.1] DepMap read failed for %s: %s", symbol, exc)
        return {
            "chronos_median": None, "is_core_essential": False,
            "selective_fraction": 0.0, "is_in_depmap": False, "n_lines": 0,
        }

    if series.empty:
        return {
            "chronos_median": None, "is_core_essential": False,
            "selective_fraction": 0.0, "is_in_depmap": False, "n_lines": 0,
        }

    vals = series.to_numpy(dtype=float)
    median = float(np.median(vals))
    selective_fraction = float(np.mean(vals < _DEPENDENCY_THRESHOLD))
    # Pan-essential: deeply negative median AND essential in the vast majority of lines.
    is_core = median < _CORE_ESSENTIAL_MEDIAN and selective_fraction > 0.9

    return {
        "chronos_median": round(median, 4),
        "is_core_essential": is_core,
        "selective_fraction": round(selective_fraction, 4),
        "is_in_depmap": True,
        "n_lines": int(len(vals)),
    }


def batch_essentiality(symbols: List[str]) -> Dict[str, Dict]:
    """
    Efficient multi-gene lookup: reads all requested columns in a single pass.
    """
    col_map = _column_index()
    cols = {s: col_map[s] for s in symbols if s in col_map}
    out: Dict[str, Dict] = {
        s: {"chronos_median": None, "is_core_essential": False,
            "selective_fraction": 0.0, "is_in_depmap": False, "n_lines": 0}
        for s in symbols
    }
    if not cols:
        return out

    path = settings.DB_DEPMAP / "CRISPRGeneEffect.csv"
    try:
        df = pd.read_csv(path, usecols=list(cols.values()))
    except Exception as exc:
        log.warning("[2.1] DepMap batch read failed: %s", exc)
        return out

    for sym, col in cols.items():
        series = df[col].dropna()
        if series.empty:
            continue
        vals = series.to_numpy(dtype=float)
        median = float(np.median(vals))
        sel = float(np.mean(vals < _DEPENDENCY_THRESHOLD))
        out[sym] = {
            "chronos_median": round(median, 4),
            "is_core_essential": median < _CORE_ESSENTIAL_MEDIAN and sel > 0.9,
            "selective_fraction": round(sel, 4),
            "is_in_depmap": True,
            "n_lines": int(len(vals)),
        }
    log.info("[2.1] Essentiality resolved for %d/%d genes in DepMap", len(cols), len(symbols))
    return out
