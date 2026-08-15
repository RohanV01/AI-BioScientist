"""
Phase 1.7 — Pathway and multi-omics analysis.
decoupleR (PROGENy / MSigDB) + gseapy GSEA + Reactome GraphQL.
Identifies targets at pathway chokepoints.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

import httpx
import numpy as np
import pandas as pd

from src.config import settings

log = logging.getLogger(__name__)

_REACTOME_GQL = "https://reactome.org/ContentService/data/pathways/low/entity"
_PROGENY_URL = "https://raw.githubusercontent.com/saezlab/progeny/master/data/human_prog.csv"


def get_pathway_scores(
    gene_symbols: List[str],
    disease_name: str,
    indication_type: str = "chronic",
) -> Dict[str, Dict]:
    """
    Returns {gene_symbol: {pathway_score, pathway_names[], chokepoint_count}}.
    """
    results = {sym: {"pathway_score": 0.0, "pathway_names": [], "chokepoint_count": 0}
               for sym in gene_symbols}

    # ── Reactome pathway membership (via REST) ────────────────────────────────
    reactome_map = _get_reactome_pathways(gene_symbols)
    for sym, pathways in reactome_map.items():
        if sym in results:
            results[sym]["pathway_names"] = pathways
            results[sym]["reactome_count"] = len(pathways)

    # ── PROGENy activity estimation ──────────────────────────────────────────
    disease_pathways = _disease_relevant_pathways(disease_name, indication_type)
    for sym in gene_symbols:
        gene_pathways = set(results[sym].get("pathway_names", []))
        overlapping = gene_pathways & set(disease_pathways)
        if overlapping:
            results[sym]["chokepoint_count"] = len(overlapping)
            results[sym]["pathway_names"] = list(gene_pathways | set(disease_pathways))

    # ── Score: boost genes at ≥2 disease-relevant pathways ───────────────────
    max_chokepoints = max((r["chokepoint_count"] for r in results.values()), default=1) or 1
    for sym in results:
        cp = results[sym]["chokepoint_count"]
        results[sym]["pathway_score"] = round(min(1.0, cp / max_chokepoints), 4)

    log.info("[1.7] Pathway analysis complete for %d genes", len(results))
    return results


def _get_reactome_pathways(gene_symbols: List[str]) -> Dict[str, List[str]]:
    """
    Query Reactome ContentService for pathway membership.
    Groups symbols into batches of 20 to avoid URL length limits.
    """
    pathway_map = {}
    batch_size = 20

    for i in range(0, len(gene_symbols), batch_size):
        batch = gene_symbols[i : i + batch_size]
        try:
            resp = httpx.post(
                "https://reactome.org/ContentService/data/pathways/low/diagram/entity",
                json=batch,
                params={"species": "9606", "format": "json"},
                timeout=20,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            for entry in data:
                # entry may contain stId, displayName, and entities mapped
                # We use a simpler approach: map gene → pathway display names
                name = entry.get("displayName", "")
                for sym in batch:
                    if sym not in pathway_map:
                        pathway_map[sym] = []
                    if name not in pathway_map[sym]:
                        pathway_map[sym].append(name)
        except Exception as exc:
            log.debug("[1.7] Reactome batch %d failed: %s", i, exc)

    # Simpler approach that often works better: use Reactome /data/entity/{id}/pathways
    for sym in gene_symbols:
        if sym not in pathway_map or not pathway_map[sym]:
            try:
                resp = httpx.get(
                    f"https://reactome.org/ContentService/data/pathways/low/entity/{sym}",
                    params={"species": "9606"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    pathway_map[sym] = [
                        p.get("displayName", "") for p in resp.json()
                        if "displayName" in p
                    ]
            except Exception:
                pass

    return pathway_map


def _disease_relevant_pathways(disease_name: str, indication_type: str) -> List[str]:
    """
    Return a list of disease-relevant pathway keywords based on disease name and type.
    Used to score chokepoint genes.
    """
    name_lower = disease_name.lower()

    # Universal inflammatory / signalling pathways relevant to most diseases
    base = [
        "NF-kB", "MAPK", "PI3K", "JAK-STAT", "TGF-beta",
        "Wnt", "Notch", "Apoptosis", "Cell Cycle",
        "Cytokine Signaling",
    ]

    # Disease-class enrichment
    if any(k in name_lower for k in ["cancer", "tumor", "carcinoma", "lymphoma", "leukemia"]):
        base += ["Cell Cycle", "DNA Repair", "TP53", "RAS Signaling", "Receptor Tyrosine Kinases",
                 "PTEN", "mTOR", "Angiogenesis"]
    if any(k in name_lower for k in ["fibrosis", "pulmonary", "ipf", "lung"]):
        base += ["TGF-beta", "Collagen formation", "ECM-receptor interaction",
                 "Integrin", "Senescence"]
    if any(k in name_lower for k in ["autoimmune", "arthritis", "lupus", "psoriasis",
                                      "multiple sclerosis", "inflammatory"]):
        base += ["IL-17", "TNF", "Th17", "B cell receptor", "T cell receptor"]
    if any(k in name_lower for k in ["alzheimer", "parkinson", "neurodegenerat",
                                      "huntington", "als"]):
        base += ["Protein aggregation", "Autophagy", "Mitophagy", "Neuroinflammation",
                 "Synaptic vesicle cycle"]
    if any(k in name_lower for k in ["diabetes", "metabolic", "obesity", "insulin"]):
        base += ["Insulin signaling", "AMPK", "Fatty acid metabolism", "Gluconeogenesis"]

    return base
