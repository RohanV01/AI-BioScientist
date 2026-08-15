"""
Phase 4 — LINCS reverse-signature signal.

Two execution paths:

  Path A — CLUE API (full LINCS L1000, activates on CLUE_API_KEY)
    B7 fix: replaced broken TAS proxy with a proper CMap gene-set query.
    Submits disease up/dn genes as a binary perturbation vector to the
    /api/query endpoint and retrieves per-perturbagen τ scores.
    Threshold: τ < −90 (strong reversal). Normalised [0,1].

  Path B — L1000CDS² (free, no key, maayanlab.cloud)
    POST /query with up/dn gene sets → ranked perturbagen list.
    Score = linear decay on rank (rank 1 → 1.0, rank 50 → 0.0).
    Active by default when CLUE_API_KEY is absent.

Disease signature — B1 fix (indication-specific dn genes):
  The previous version used a universal cancer TSG fallback for ALL indications,
  which produced biologically meaningless dn gene lists for CNS, cardiovascular,
  and autoimmune diseases.

  New three-tier strategy:
    1. Phase 2 DepMap Chronos (non-essential genes = suppressor-like)
    2. Open Targets EFO-specific LoF genes (queried from OT GraphQL API)
    3. Indication-type-specific fallback dictionaries:
         oncology     → cancer TSGs (CDKN2A, PTEN, RB1, TP53…)
         cns          → neurodegeneration protectors (PARK2, PINK1, GBA…)
         autoimmune   → immune suppressors (FOXP3, IL10, CTLA4…)
         cardiovascular → cardiac protectors (PTEN, TP53, SMAD3…)
         chronic/acute → broad housekeeping TSG subset
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

_CLUE_API_BASE   = "https://api.clue.io/api"
_L1000CDS2_URL   = "https://maayanlab.cloud/L1000CDS2/query"
_OT_GQL_URL      = "https://api.platform.opentargets.org/api/v4/graphql"
_REQUEST_TIMEOUT = 30
_L1000_TOP_N     = 50

# B7: CLUE τ normalization
_TAU_REVERSAL_MIN = -90.0    # below this = meaningful reversal
_TAU_REVERSAL_MAX = -150.0   # ceiling (full 1.0 score)


# ─────────────────────────────────────────────────────────────────────────────
# B1 fix — indication-specific dn gene fallbacks
# ─────────────────────────────────────────────────────────────────────────────

_DN_GENES_BY_INDICATION: Dict[str, List[str]] = {
    # Cancer: established tumor suppressors across ≥5 cancer types
    # (Vogelstein 2013, Science; Sondka 2018, Nature Rev Cancer; COSMIC Census)
    "oncology": [
        "TP53", "CDKN2A", "PTEN", "RB1", "APC", "VHL", "MLH1", "MSH2",
        "BRCA1", "BRCA2", "SMAD4", "NF1", "NF2", "TSC1", "TSC2",
        "ATM", "CHEK2", "CDH1", "STK11", "PALB2", "BAP1", "FBXW7",
    ],
    # CNS / neurodegeneration: genes lost in Parkinson's, Alzheimer's, ALS
    # (Bharat 2021 NatRevNeuro; OMIM; GeneReviews)
    "cns": [
        "PARK2", "PINK1", "DJ1", "ATP13A2", "FBXO7", "GBA", "LRRK2",
        "SNCA", "MAPT", "SOD1", "TARDBP", "FUS", "C9orf72", "OPTN",
        "APP", "PSEN1", "PSEN2", "APOE",
    ],
    # Autoimmune: immune regulatory genes suppressed in autoimmune disease
    # (Goodnow 2007 Nature; Bluestone 2010 Immunity; OMIM immune dysregulation)
    "autoimmune": [
        "FOXP3", "IL10", "TGFB1", "CTLA4", "IL2RA", "CD25", "PDCD1",
        "LAIR1", "TIGIT", "IL10RA", "IL10RB", "STAT3", "TNFAIP3",
        "SH2B3", "PTPN22",
    ],
    # Cardiovascular: cardioprotective / anti-fibrotic genes
    # (Harvey 2007 NatRevGenet; OMIM cardiomyopathy; Wamstad 2012 Cell)
    "cardiovascular": [
        "PTEN", "TP53", "CDKN1A", "RB1", "SMAD3", "TGFBR2", "ACE2",
        "NKX2-5", "GATA4", "TBX5", "MYH7", "PLN", "HIF1A", "VEGFA",
    ],
    # Metabolic / chronic (broad, not cancer-specific)
    "chronic": [
        "TP53", "PTEN", "SMAD4", "RB1", "CDKN1A", "CDKN2A",
        "TGFB1", "SMAD3", "VHL", "NF1",
    ],
    # Acute / infectious: immune and barrier defence genes
    "acute": [
        "TP53", "PTEN", "RB1", "STAT1", "IRF3", "IRF7",
        "IFNAR1", "IFNAR2", "IFNGR1", "MAVS",
    ],
}


def _dn_genes_from_indication(indication_type: str) -> List[str]:
    """Return indication-specific dn gene fallback list."""
    key = (indication_type or "chronic").lower()
    return list(_DN_GENES_BY_INDICATION.get(key, _DN_GENES_BY_INDICATION["chronic"]))


# ─────────────────────────────────────────────────────────────────────────────
# B1: Open Targets EFO-specific LoF gene query
# ─────────────────────────────────────────────────────────────────────────────

def _dn_genes_from_open_targets(efo_id: str, max_genes: int = 30) -> List[str]:
    """
    Query Open Targets for genes with loss-of-function genetic evidence for efo_id.

    Filters: datasource = 'eva' or 'gene_burden' (rare variant burden tests,
    enriched for TSG loss-of-function). Returns gene symbols sorted by score desc.
    Falls back to [] on any error.

    Scientific basis: OT rare variant / EVA evidence for a disease strongly
    indicates causal loss-of-function — these genes are genuinely suppressed or
    lost in the disease context (Mountjoy et al. 2021, Nature Genet).
    """
    if not efo_id:
        return []
    query = """
    query diseaseTargets($efoId: String!, $size: Int!) {
      disease(efoId: $efoId) {
        associatedTargets(page: {index: 0, size: $size}) {
          rows {
            target { approvedSymbol }
            datasourceScores {
              id
              score
            }
          }
        }
      }
    }
    """
    try:
        resp = requests.post(
            _OT_GQL_URL,
            json={"query": query, "variables": {"efoId": efo_id, "size": 200}},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        rows = (
            resp.json()
            .get("data", {})
            .get("disease", {})
            .get("associatedTargets", {})
            .get("rows", [])
        )
        # Keep genes where 'eva' or 'gene_burden' datasource has evidence
        # (rare LoF variant evidence = likely suppressor/loss in disease)
        dn = []
        for row in rows:
            scores = {ds["id"]: ds["score"] for ds in row.get("datasourceScores", [])}
            if scores.get("eva", 0) > 0 or scores.get("gene_burden", 0) > 0:
                sym = row.get("target", {}).get("approvedSymbol")
                if sym:
                    dn.append(sym)
            if len(dn) >= max_genes:
                break
        log.info("[4.lincs] OT LoF dn genes for %s: %d genes", efo_id, len(dn))
        return dn
    except Exception as exc:
        log.debug("[4.lincs] OT dn gene query failed for %s: %s", efo_id, exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_lincs_score(
    drug_name: str,
    gene_symbol: str,
    disease_up_genes: List[str],
    disease_dn_genes: List[str],
) -> float:
    """Return a LINCS reverse-signature score [0.0, 1.0] for a drug candidate."""
    if not disease_up_genes and not disease_dn_genes:
        return 0.0

    clue_key = os.environ.get("CLUE_API_KEY")
    if clue_key:
        return _score_via_clue(drug_name, disease_up_genes, disease_dn_genes, clue_key)
    return _score_via_l1000cds2(drug_name, disease_up_genes, disease_dn_genes)


# ─────────────────────────────────────────────────────────────────────────────
# Path A — CLUE API with proper τ query (B7 fix)
# ─────────────────────────────────────────────────────────────────────────────

# Module-level cache: (frozenset(up), frozenset(dn)) → {drug_name_upper: tau}
_CLUE_TAU_CACHE: Dict[Tuple, Dict[str, float]] = {}


def _score_via_clue(
    drug_name: str,
    up_genes: List[str],
    dn_genes: List[str],
    api_key: str,
) -> float:
    """
    B7 fix: proper CMap τ query via CLUE API gene-set submission.

    Submits a binary gene expression vector (up_genes=+1, dn_genes=-1, rest=0)
    to POST /api/query and retrieves per-perturbagen τ scores.
    τ < −90 = meaningful reversal; τ < −150 = maximal reversal.

    Results are cached per signature to avoid redundant API calls.
    """
    cache_key = (frozenset(up_genes[:100]), frozenset(dn_genes[:50]))
    if cache_key not in _CLUE_TAU_CACHE:
        _CLUE_TAU_CACHE[cache_key] = _fetch_clue_tau(up_genes, dn_genes, api_key)

    tau_map = _CLUE_TAU_CACHE.get(cache_key, {})
    tau = tau_map.get(drug_name.upper().strip(), 0.0)

    if tau >= _TAU_REVERSAL_MIN:
        return 0.0
    # Normalise: τ=−90 → 0.0, τ=−150 → 1.0 (linear)
    score = (_TAU_REVERSAL_MIN - tau) / (_TAU_REVERSAL_MIN - _TAU_REVERSAL_MAX)
    return round(min(1.0, max(0.0, score)), 4)


def _fetch_clue_tau(
    up_genes: List[str],
    dn_genes: List[str],
    api_key: str,
) -> Dict[str, float]:
    """
    Submit a gene-set query to CLUE /api/query.

    Returns dict: drug_name_upper → best τ score (most negative across cell lines).
    """
    # Step 1: build the query vector (up/dn gene symbols)
    headers = {
        "user_key": api_key,
        "Content-Type": "application/json",
    }
    query_payload = {
        "data": {
            "upGenes": [g.upper() for g in up_genes[:150]],
            "dnGenes": [g.upper() for g in dn_genes[:50]],
        },
        "config": {
            "aggravate": False,
            "searchMethod": "geneSet",
            "db-version": "latest",
        },
    }
    try:
        # CLUE query endpoint (returns a job ID, then poll for results)
        r = requests.post(
            f"{_CLUE_API_BASE}/query",
            json=query_payload,
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        job = r.json()
        job_id = job.get("_id") or job.get("id")
        if not job_id:
            log.warning("[4.lincs] CLUE query: no job_id in response")
            return {}

        # Poll until job completes (max 60 s)
        for _ in range(20):
            time.sleep(3)
            status_r = requests.get(
                f"{_CLUE_API_BASE}/query/{job_id}/status",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            status_r.raise_for_status()
            status = status_r.json().get("status", "")
            if status == "completed":
                break
            if status == "failed":
                log.warning("[4.lincs] CLUE job %s failed", job_id)
                return {}
        else:
            log.warning("[4.lincs] CLUE job %s timed out", job_id)
            return {}

        # Retrieve results
        results_r = requests.get(
            f"{_CLUE_API_BASE}/query/{job_id}/result",
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
        results_r.raise_for_status()
        results = results_r.json()

        # Build drug → best τ map
        tau_map: Dict[str, float] = {}
        for entry in results:
            name = str(
                entry.get("pert_iname") or entry.get("pert_desc") or ""
            ).upper().strip()
            tau = float(entry.get("tau", 0))
            if name and tau < 0:
                tau_map[name] = min(tau_map.get(name, 0.0), tau)

        log.info("[4.lincs] CLUE τ query: %d perturbagens with τ<0", len(tau_map))
        return tau_map

    except Exception as exc:
        log.warning("[4.lincs] CLUE τ query failed: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Path B — L1000CDS² (free, no key)
# ─────────────────────────────────────────────────────────────────────────────

_L1000CDS2_CACHE: Dict[Tuple, Dict[str, float]] = {}


def _score_via_l1000cds2(
    drug_name: str,
    up_genes: List[str],
    dn_genes: List[str],
) -> float:
    """Query L1000CDS² for rank-based reversal score."""
    cache_key = (frozenset(up_genes[:150]), frozenset(dn_genes[:150]))
    if cache_key not in _L1000CDS2_CACHE:
        _L1000CDS2_CACHE[cache_key] = _fetch_l1000cds2_rankings(up_genes, dn_genes)
    rankings = _L1000CDS2_CACHE.get(cache_key, {})
    return rankings.get(drug_name.upper().strip(), 0.0)


def _fetch_l1000cds2_rankings(
    up_genes: List[str],
    dn_genes: List[str],
) -> Dict[str, float]:
    """Fetch ranked perturbagens from L1000CDS². Returns drug_upper → score [0,1]."""
    payload = {
        "data": {
            "upGenes": [g.upper() for g in up_genes[:500]],
            "dnGenes": [g.upper() for g in dn_genes[:500]],
        },
        "config": {
            "aggravate": False,
            "searchMethod": "geneSet",
            "share": False,
            "combination": False,
            "db-version": "latest",
        },
    }
    try:
        r = requests.post(_L1000CDS2_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        if "err" in data:
            log.warning("[4.lincs] L1000CDS2 error: %s", data["err"])
            return {}
        rankings: Dict[str, float] = {}
        for i, entry in enumerate(data.get("topMeta", [])[:_L1000_TOP_N]):
            name = str(
                entry.get("pert_desc") or entry.get("pert_iname") or ""
            ).upper().strip()
            if name:
                score = round(max(0.0, 1.0 - i / _L1000_TOP_N), 4)
                rankings[name] = max(rankings.get(name, 0.0), score)
        log.info("[4.lincs] L1000CDS2: %d perturbagens ranked", len(rankings))
        return rankings
    except Exception as exc:
        log.warning("[4.lincs] L1000CDS2 request failed: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Disease signature builder — B1 fix
# ─────────────────────────────────────────────────────────────────────────────

_CANCER_TSG_FALLBACK = _DN_GENES_BY_INDICATION["oncology"]


def build_disease_signature(
    ranked_targets: List[Dict],
    validated_targets: Optional[List[Dict]] = None,
    indication_type: str = "chronic",
    disease_efo_id: Optional[str] = None,
    top_n_up: int = 100,
    top_n_dn: int = 50,
) -> Tuple[List[str], List[str]]:
    """
    Build a disease up/dn gene signature for L1000CDS² / CLUE.

    Up genes: top-N Phase 1 ranked targets by PU score.

    Dn genes (priority order):
      1. Phase 2 DepMap Chronos > -0.1 (non-essential = suppressor-like)
      2. Phase 1 evidence_trail.depmap_chronos (populated when P2 ran first)
      3. Open Targets EFO LoF genes (rare variant burden evidence)
      4. Indication-type-specific fallback dictionary (B1 fix)

    L1000CDS² requires ≥ 3 genes in each list; falls back to next tier as needed.
    """
    sorted_targets = sorted(
        ranked_targets,
        key=lambda t: float(t.get("aggregate_score") or t.get("score") or 0),
        reverse=True,
    )
    up = [t["symbol"] for t in sorted_targets[:top_n_up] if t.get("symbol")]
    up_set = set(up)

    dn: List[str] = []

    # Tier 1: Phase 2 essentiality
    if validated_targets:
        for vt in validated_targets:
            sym = vt.get("symbol")
            chronos = vt.get("essentiality", {}).get("chronos")
            if sym and chronos is not None and float(chronos) > -0.1 and sym not in up_set:
                dn.append(sym)
        dn = dn[:top_n_dn]

    # Tier 2: Phase 1 evidence_trail
    if not dn:
        for t in sorted_targets:
            sym = t.get("symbol")
            chronos = t.get("evidence_trail", {}).get("depmap_chronos")
            if sym and chronos is not None and float(chronos) > -0.1 and sym not in up_set:
                dn.append(sym)
        dn = dn[:top_n_dn]

    # Tier 3: Open Targets EFO-specific LoF (B1 fix — indication-specific)
    if len(dn) < 3 and disease_efo_id:
        ot_dn = _dn_genes_from_open_targets(disease_efo_id, max_genes=30)
        existing = set(dn) | up_set
        dn += [g for g in ot_dn if g not in existing]
        dn = dn[:top_n_dn]

    # Tier 4: indication-type-specific fallback (B1 fix — replaces universal TSG list)
    if len(dn) < 3:
        fallback = _dn_genes_from_indication(indication_type)
        existing = set(dn) | up_set
        dn += [g for g in fallback if g not in existing]
        dn = dn[:top_n_dn]
        log.info(
            "[4.lincs] Using %s fallback for dn genes (%d genes)",
            indication_type, len(dn),
        )

    return up, dn
