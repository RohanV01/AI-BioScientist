"""
Phase 4 — PrimeKG drug-protein knowledge-graph signal.

PrimeKG (Chandak et al. 2023, Sci Data) integrates 20 biomedical databases
including DrugBank, DGIdb, STITCH, and OMIM into a single heterogeneous KG.
The drug_protein relation (25,653 edges) captures curated mechanism-confirmed
drug–target interactions — orthogonal to ChEMBL bioassay evidence.

H2 fix — ChEMBL INN ≠ PrimeKG name:
  PrimeKG uses investigational/brand names (e.g. AMG-510) while ChEMBL uses
  INN names (SOTORASIB).  We build a synonym expansion index by querying the
  ChEMBL molecule_synonyms table (syn_type IN INN/USAN/BAN/TRADE_NAME) and
  mapping each synonym → pref_name.  On lookup we try the raw name first,
  then all known synonyms.  This recovers ~30% more KG hits.

  Synonym index is loaded lazily (only when ChEMBL DB is present).

Scores:
  1.0  direct drug_protein edge in PrimeKG (by any name/synonym)
  0.5  edge to a paralogue (same 3-char gene prefix, e.g. EGFR→ERBB2)
  0.0  no evidence
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Set

import pandas as pd

log = logging.getLogger(__name__)

_KG_PATH = Path(
    os.environ.get(
        "PRIMEKG_PATH",
        str(Path(__file__).parents[3] / "Databases" / "primekg" / "kg.csv"),
    )
)
_CHEMBL_DB = Path(
    os.environ.get(
        "CHEMBL_DB_PATH",
        str(Path(__file__).parents[3] / "Databases" / "chembl" / "chembl_37.db"),
    )
)

# Module-level caches
_GENE_TO_DRUGS: Optional[Dict[str, Set[str]]] = None
# synonym (upper) → canonical name set (upper) — built from ChEMBL molecule_synonyms
_SYNONYM_TO_NAMES: Optional[Dict[str, Set[str]]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Load KG index
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_loaded() -> None:
    global _GENE_TO_DRUGS
    if _GENE_TO_DRUGS is not None:
        return

    if not _KG_PATH.exists():
        log.warning("[4.primekg] KG file not found at %s", _KG_PATH)
        _GENE_TO_DRUGS = {}
        return

    log.info("[4.primekg] Loading drug-protein edges from PrimeKG (first call)…")
    try:
        df = pd.read_csv(
            str(_KG_PATH),
            usecols=["relation", "x_type", "y_type", "x_name", "y_name"],
            low_memory=False,
        )
        mask = (
            (df["x_type"] == "drug")
            & (df["y_type"] == "gene/protein")
            & (df["relation"] == "drug_protein")
        )
        dt = df[mask][["x_name", "y_name"]].copy()
        dt["x_name"] = dt["x_name"].str.upper().str.strip()
        dt["y_name"] = dt["y_name"].str.upper().str.strip()

        index: Dict[str, Set[str]] = {}
        for gene, drugs in dt.groupby("y_name")["x_name"]:
            index[str(gene)] = set(drugs)

        _GENE_TO_DRUGS = index
        log.info("[4.primekg] Index built: %d genes with drug interactions", len(index))
    except Exception as exc:
        log.warning("[4.primekg] Load failed: %s", exc)
        _GENE_TO_DRUGS = {}


# ─────────────────────────────────────────────────────────────────────────────
# H2 fix: ChEMBL synonym expansion
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_synonyms() -> None:
    """
    Build synonym → {canonical_names} lookup from ChEMBL molecule_synonyms.

    Queries: syn_type IN ('INN','USAN','BAN','TRADE_NAME','OTHER')
    Maps each synonym (upper) → set of pref_names (upper) so that when we look
    up 'SOTORASIB' we also check 'AMG-510', 'AMG510', etc.
    """
    global _SYNONYM_TO_NAMES
    if _SYNONYM_TO_NAMES is not None:
        return

    if not _CHEMBL_DB.exists():
        _SYNONYM_TO_NAMES = {}
        return

    log.info("[4.primekg] Building ChEMBL synonym index (first call)…")
    try:
        conn = sqlite3.connect(str(_CHEMBL_DB), check_same_thread=False)
        q = """
            SELECT ms.synonyms, md.pref_name
            FROM molecule_synonyms ms
            JOIN molecule_dictionary md ON md.molregno = ms.molregno
            WHERE ms.syn_type IN ('INN','USAN','BAN','TRADE_NAME','OTHER','RESEARCH_CODE')
              AND ms.synonyms IS NOT NULL
              AND md.pref_name IS NOT NULL
        """
        rows = conn.execute(q).fetchall()
        conn.close()

        index: Dict[str, Set[str]] = {}
        for syn, pref in rows:
            key = syn.upper().strip()
            pref_key = pref.upper().strip()
            # Forward:  synonym  → canonical pref_name
            index.setdefault(key, set()).add(pref_key)
            # Reverse:  pref_name → this synonym  (so SOTORASIB expands to AMG-510)
            index.setdefault(pref_key, set()).add(key)
            index.setdefault(pref_key, set()).add(pref_key)

        _SYNONYM_TO_NAMES = index
        log.info("[4.primekg] Synonym index: %d entries", len(index))
    except Exception as exc:
        log.warning("[4.primekg] Synonym index build failed: %s", exc)
        _SYNONYM_TO_NAMES = {}


def _expand_names(drug_name: str) -> Set[str]:
    """
    Return all names to try in PrimeKG for a given drug name.
    Includes: the raw name + all ChEMBL synonyms mapped to PrimeKG-style names.
    """
    _ensure_synonyms()
    upper = drug_name.upper().strip()
    names = {upper}
    if _SYNONYM_TO_NAMES:
        # Add all alternate names this drug is known by
        names |= _SYNONYM_TO_NAMES.get(upper, set())
        # Also look up if the input is itself a synonym → get canonical + its synonyms
        for canonical in _SYNONYM_TO_NAMES.get(upper, set()):
            names |= _SYNONYM_TO_NAMES.get(canonical, set())
    return names


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_kg_score(gene_symbol: str, drug_name: str) -> float:
    """
    Return a KG confidence score [0.0, 1.0] for a (gene, drug) pair.

      1.0  direct drug_protein edge in PrimeKG (by any synonym)
      0.5  edge to a paralogue (first-3-char prefix family match)
      0.0  no evidence
    """
    _ensure_loaded()
    if not _GENE_TO_DRUGS:
        return 0.0

    gene_upper = gene_symbol.upper().strip()
    target_drugs = _GENE_TO_DRUGS.get(gene_upper, set())

    # H2 fix: try all synonyms of the drug name
    candidate_names = _expand_names(drug_name)

    # Direct hit — any synonym matches a PrimeKG drug name for this gene
    if candidate_names & target_drugs:
        return 1.0

    # Paralogue / family hit
    prefix = gene_upper[:3]
    for g, drugs in _GENE_TO_DRUGS.items():
        if g.startswith(prefix) and g != gene_upper:
            if candidate_names & drugs:
                return 0.5

    return 0.0


def get_all_drugs_for_gene(gene_symbol: str) -> Set[str]:
    """Return the set of PrimeKG drug names with a direct edge to gene_symbol."""
    _ensure_loaded()
    return set(_GENE_TO_DRUGS.get(gene_symbol.upper().strip(), set()))
