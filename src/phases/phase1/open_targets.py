"""
Phase 1.2 — Open Targets association pull + Pharos TDL annotation.
"""
from __future__ import annotations
import logging
import time
from typing import Dict, List, Set

import httpx

log = logging.getLogger(__name__)

_OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
_PHAROS_GQL = "https://pharos-api.ncats.io/graphql"


def _ot_post_with_retry(payload: dict, retries: int = 4, timeout: int = 90) -> dict:
    """POST to OT GraphQL with retry on transient 5xx / timeouts (the API gateway hiccups)."""
    last_exc = None
    for attempt in range(retries):
        try:
            resp = httpx.post(_OT_GQL, json=payload, timeout=timeout)
            if resp.status_code >= 500:
                log.warning("[OT] HTTP %d (attempt %d/%d), retrying", resp.status_code, attempt + 1, retries)
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            log.warning("[OT] %s (attempt %d/%d), retrying", type(exc).__name__, attempt + 1, retries)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Open Targets GraphQL failed after {retries} attempts: {last_exc}")

_OT_QUERY = """
query DiseaseTargets($efoId: String!, $page: Int!) {
  disease(efoId: $efoId) {
    associatedTargets(page: {index: $page, size: 50}) {
      count
      rows {
        target {
          id
          approvedSymbol
          biotype
          tractability { modality label value }
        }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""


def pull_ot_associations(
    efo_id: str,
    min_score: float = 0.1,
    cap: int = 300,
    seed_targets: Set[str] = frozenset(),
    exclude_targets: Set[str] = frozenset(),
) -> List[Dict]:
    """
    Returns a list of target dicts with OT association data.
    seed_targets are force-included even if below min_score.
    exclude_targets are never returned.
    """
    all_rows = []
    page = 0

    while len(all_rows) < cap:
        resp_json = _ot_post_with_retry({"query": _OT_QUERY, "variables": {"efoId": efo_id, "page": page}})
        data = resp_json["data"]["disease"]["associatedTargets"]
        rows = data["rows"]
        total = data["count"]

        if not rows:
            break

        all_rows.extend(rows)
        page += 1

        if len(all_rows) >= total or len(all_rows) >= cap:
            break

    log.info("[1.2] OT returned %d associations for %s", len(all_rows), efo_id)

    # Rare-disease edge case: if very few targets, loosen cutoff
    effective_min = min_score
    if len([r for r in all_rows if r["score"] >= min_score]) < 5:
        effective_min = 0.05
        log.info("[1.2] Rare-disease mode: loosened cutoff to %.2f", effective_min)

    targets = []
    for row in all_rows:
        symbol = row["target"]["approvedSymbol"]
        ensembl_id = row["target"]["id"]

        if symbol in exclude_targets or ensembl_id in exclude_targets:
            continue

        score = row["score"]
        is_seeded = symbol in seed_targets or ensembl_id in seed_targets

        if score < effective_min and not is_seeded:
            continue

        # Extract tractability — OT v4 returns a list of {modality, label, value}
        tract_list = row["target"].get("tractability") or []
        tractability_max = _tractability_score(tract_list)

        # Datatype scores breakdown
        dt_scores = {d["id"]: d["score"] for d in row.get("datatypeScores", [])}

        targets.append({
            "ensembl_id": ensembl_id,
            "symbol": symbol,
            "biotype": row["target"].get("biotype", ""),
            "ot_assoc_score": round(score, 4),
            "tractability_max": round(tractability_max, 4),
            "dt_scores": dt_scores,
            "seeded": is_seeded,
        })

    log.info("[1.2] After filter: %d targets (min_score=%.2f)", len(targets), effective_min)
    return targets[:cap]


# Tractability bucket → tier score. OT v4 gives a list of {modality, label, value};
# we take the highest tier among buckets that are true (value == True).
_TRACT_TIERS = {
    "Approved Drug": 1.0,
    "Advanced Clinical": 0.9,
    "Phase 1 Clinical": 0.8,
    "Structure with Ligand": 0.65,
    "High-Quality Ligand": 0.6,
    "High-Quality Pocket": 0.55,
    "Med-Quality Pocket": 0.45,
    "Druggable Family": 0.4,
    "UniProt loc high conf": 0.5,
    "GO CC high conf": 0.45,
    "UniProt loc med conf": 0.35,
    "GO CC med conf": 0.3,
    "Human Protein Atlas loc": 0.3,
    "UniProt SigP or TMHMM": 0.3,
}


def _tractability_score(tract_list: List[Dict]) -> float:
    """Highest tier among true tractability buckets; 0.2 floor if any true, else 0."""
    best = 0.0
    any_true = False
    for entry in tract_list:
        if not entry.get("value"):
            continue
        any_true = True
        best = max(best, _TRACT_TIERS.get(entry.get("label", ""), 0.2))
    return best if any_true else 0.0


def get_disease_xrefs(efo_id: str, prefix: str = "DOID") -> List[str]:
    """
    Fetch cross-reference IDs for a disease from Open Targets (e.g. DOID:1793).
    Used to broaden Jensen DISEASES lookups beyond name matching.
    Returns a list of ID strings with the given prefix (e.g. ["DOID:1793"]).
    """
    query = """
    query DiseaseXrefs($efoId: String!) {
      disease(efoId: $efoId) { dbXRefs }
    }
    """
    try:
        resp = _ot_post_with_retry({"query": query, "variables": {"efoId": efo_id}}, retries=2)
        refs = resp.get("data", {}).get("disease", {}).get("dbXRefs") or []
        return [r for r in refs if r.startswith(prefix)]
    except Exception as exc:
        log.warning("[OT] dbXRefs fetch failed: %s", exc)
        return []


_PHAROS_QUERY = """
query TDL($symbols: [String!]!) {
  targets(targets: $symbols) {
    sym
    tdl
    novelty
  }
}
"""


def annotate_pharos_tdl(targets: List[Dict]) -> Dict[str, Dict]:
    """
    Add TDL (Tclin/Tchem/Tbio/Tdark) to each target.
    Returns a dict keyed by symbol with {tdl, novelty}.
    """
    symbols = [t["symbol"] for t in targets]
    batch_size = 50
    tdl_map = {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            resp = httpx.post(
                _PHAROS_GQL,
                json={"query": _PHAROS_QUERY, "variables": {"symbols": batch}},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()["data"]["targets"] or []
            for entry in data:
                tdl_map[entry["sym"]] = {
                    "tdl": entry.get("tdl", "Tbio"),
                    "novelty": entry.get("novelty", 0),
                }
        except Exception as exc:
            log.warning("[1.3] Pharos TDL batch failed: %s", exc)

    return tdl_map
