"""
ChEMBL chemical-matter check (local SQLite, read-only).

Used by Phase 2.8 (modality eligibility) and Phase 3 (SM scoring, repurposing).
Given a UniProt accession we count distinct bioactive compounds tested against
that target and the highest clinical phase among them:

  n_bioactive        distinct molecules with a recorded activity
  n_potent           distinct molecules with pchembl_value >= 6 (≈ ≤1 µM)
  max_phase          max molecule_dictionary.max_phase (4 = approved)
  has_chemical_matter n_potent >= 10  (tractable chemical series exists)

ChEMBL 37 schema joins:
  component_sequences.accession → target_components → target_dictionary
  → assays → activities → molecule_dictionary
"""
from __future__ import annotations
import logging
import sqlite3
from functools import lru_cache
from typing import Dict, Optional

from src.config import settings

log = logging.getLogger(__name__)

_CHEMBL_DB = settings.DB_CHEMBL / "chembl_37.db"
_POTENT_CUTOFF = 10


def _connect() -> Optional[sqlite3.Connection]:
    if not _CHEMBL_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{_CHEMBL_DB}?mode=ro", uri=True, timeout=30)
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error as exc:
        log.warning("[chembl] connect failed: %s", exc)
        return None


@lru_cache(maxsize=256)
def chemical_matter(uniprot: Optional[str]) -> Dict:
    empty = {"n_bioactive": 0, "n_potent": 0, "max_phase": 0,
             "has_chemical_matter": False, "source": "none"}
    if not uniprot:
        return empty
    conn = _connect()
    if conn is None:
        return empty

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(DISTINCT act.molregno) AS n_bioactive,
                   COUNT(DISTINCT CASE WHEN act.pchembl_value >= 6
                                       THEN act.molregno END) AS n_potent,
                   COALESCE(MAX(md.max_phase), 0) AS max_phase
            FROM component_sequences cs
            JOIN target_components tc ON tc.component_id = cs.component_id
            JOIN target_dictionary td ON td.tid = tc.tid
            JOIN assays a ON a.tid = td.tid
            JOIN activities act ON act.assay_id = a.assay_id
            LEFT JOIN molecule_dictionary md ON md.molregno = act.molregno
            WHERE cs.accession = ?
              AND act.pchembl_value IS NOT NULL
            """,
            (uniprot,),
        )
        row = cur.fetchone()
    except sqlite3.Error as exc:
        log.warning("[chembl] query failed for %s: %s", uniprot, exc)
        return empty
    finally:
        conn.close()

    if not row:
        return empty

    n_bioactive, n_potent, max_phase = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    log.info("[chembl] %s: %d bioactive (%d potent), max_phase=%d",
             uniprot, n_bioactive, n_potent, max_phase)
    return {
        "n_bioactive": n_bioactive,
        "n_potent": n_potent,
        "max_phase": max_phase,
        "has_chemical_matter": n_potent >= _POTENT_CUTOFF,
        "source": "chembl",
    }
