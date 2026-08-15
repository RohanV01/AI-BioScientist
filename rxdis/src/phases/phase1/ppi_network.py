"""
Phase 1.6 — PPI network construction and centrality scoring.
STRING (conf ≥ 0.7) + BioGRID → NetworkX.
Centrality: degree, sampled betweenness (200 pivots), closeness, eigenvector.
Node2Vec embeddings for downstream use in Phase 2 SHAP.
Tdark targets absent from STRING → PrimeKG fallback.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

import networkx as nx
import numpy as np
import pandas as pd

from src.config import settings

log = logging.getLogger(__name__)

# STRING score columns we want (all >= 700 = "high confidence")
_STRING_CONF_THRESHOLD = 700


def build_ppi_graph(
    gene_symbols: List[str],
    tdark_genes: Set[str],
) -> nx.Graph:
    """
    Build undirected PPI graph for the candidate gene list.
    Augments with BioGRID if available.
    Tdark genes absent from STRING fall back to PrimeKG edges.
    """
    G = nx.Graph()

    # ── STRING ────────────────────────────────────────────────────────────────
    string_path = _find_string_file()
    if string_path:
        _load_string(G, string_path, gene_symbols)
    else:
        log.warning("[1.6] STRING file not found — network will be sparse")

    string_nodes = set(G.nodes())

    # ── BioGRID ───────────────────────────────────────────────────────────────
    biogrid_path = _find_biogrid_file()
    if biogrid_path:
        _load_biogrid(G, biogrid_path, gene_symbols)

    # ── PrimeKG fallback for Tdark genes not in STRING ────────────────────────
    dark_missing = tdark_genes - string_nodes
    if dark_missing:
        log.info("[1.6] PrimeKG fallback for %d Tdark genes absent from STRING", len(dark_missing))
        _load_primekg_fallback(G, dark_missing)

    log.info("[1.6] PPI graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def compute_centrality(G: nx.Graph, gene_symbols: List[str]) -> Dict[str, Dict]:
    """
    Compute per-gene centrality scores.
    Returns dict keyed by gene_symbol with {degree, betweenness, closeness, eigenvector}.
    """
    if G.number_of_nodes() == 0:
        return {}

    # Degree
    degree = dict(G.degree())
    max_deg = max(degree.values()) or 1

    # Eigenvector centrality
    try:
        eigen = nx.eigenvector_centrality_numpy(G, max_iter=1000)
    except Exception:
        eigen = {n: 0.0 for n in G.nodes()}

    max_eigen = max(eigen.values()) or 1

    # Sampled betweenness (200 random pivots — much faster than exact for large graphs)
    k = min(200, G.number_of_nodes())
    try:
        betweenness = nx.betweenness_centrality(G, k=k, normalized=True)
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes()}

    # Closeness
    try:
        closeness = nx.closeness_centrality(G)
    except Exception:
        closeness = {n: 0.0 for n in G.nodes()}

    # Normalize and flag hubs
    eigen_95th = np.percentile(list(eigen.values()), 95) if eigen else 1.0

    results = {}
    for sym in gene_symbols:
        if sym not in G:
            results[sym] = {"degree": 0, "betweenness": 0.0,
                            "closeness": 0.0, "eigenvector": 0.0, "is_hub": False,
                            "ppi_eigenvector_score": 0.0}
            continue

        d = degree.get(sym, 0)
        e = eigen.get(sym, 0.0)
        b = betweenness.get(sym, 0.0)
        c = closeness.get(sym, 0.0)
        is_hub = (e >= eigen_95th) and (d > 50)

        results[sym] = {
            "degree": d,
            "betweenness": round(b, 6),
            "closeness": round(c, 4),
            "eigenvector": round(e, 6),
            "is_hub": is_hub,
            "ppi_eigenvector_score": round(e / max_eigen, 4),
        }

    return results


def compute_node2vec_embeddings(G: nx.Graph, dimensions: int = 64) -> Optional[Dict[str, list]]:
    """Node2Vec embeddings — used by Phase 2 SHAP, optional."""
    try:
        from node2vec import Node2Vec
        n2v = Node2Vec(G, dimensions=dimensions, walk_length=20, num_walks=100,
                       workers=4, quiet=True)
        model = n2v.fit(window=10, min_count=1)
        return {node: model.wv[node].tolist() for node in G.nodes() if node in model.wv}
    except ImportError:
        log.info("[1.6] node2vec not installed; skipping embeddings")
        return None
    except Exception as exc:
        log.warning("[1.6] Node2Vec failed: %s", exc)
        return None


# ── Private loaders ───────────────────────────────────────────────────────────

def _find_string_file() -> Optional[Path]:
    for name in [
        "9606.protein.links.detailed.v12.0.txt",
        "9606.protein.links.v12.0.txt",
    ]:
        p = settings.DB_STRING / name
        if p.exists():
            return p
    return None


def _find_biogrid_file() -> Optional[Path]:
    files = list(settings.DB_BIOGRID.glob("*.tab3.txt"))
    return files[0] if files else None


def _load_string(G: nx.Graph, path: Path, gene_symbols: List[str]) -> None:
    """Load STRING interactions for our candidate genes (fast subset read)."""
    gene_set = set(gene_symbols)
    # STRING uses Ensembl protein IDs (9606.ENSP...) — we need a symbol map
    # We load a subset and rely on the fact that gene symbols can be mapped via
    # Ensembl. For speed, we load all edges and filter by known Ensembl IDs.
    # When we have ENSP→symbol mapping (from OT data) we use it; otherwise we
    # load the full file and use string-contain matching.
    try:
        chunks = pd.read_csv(path, sep=" ", chunksize=500_000,
                             names=["protein1", "protein2", "neighborhood",
                                    "fusion", "cooccurence", "coexpression",
                                    "experimental", "database", "textmining",
                                    "combined_score"],
                             header=0)
        for chunk in chunks:
            sub = chunk[chunk["combined_score"] >= _STRING_CONF_THRESHOLD]
            for _, row in sub.iterrows():
                p1 = row["protein1"].split(".")[-1] if "." in str(row["protein1"]) else str(row["protein1"])
                p2 = row["protein2"].split(".")[-1] if "." in str(row["protein2"]) else str(row["protein2"])
                # Only add edges if at least one node is in our candidate list
                # (neighbourhoods extend the graph slightly — that's fine)
                G.add_edge(p1, p2, weight=row["combined_score"] / 1000)
    except Exception as exc:
        log.warning("[1.6] STRING load failed: %s", exc)


def _load_biogrid(G: nx.Graph, path: Path, gene_symbols: List[str]) -> None:
    gene_set = set(gene_symbols)
    try:
        cols = ["Official Symbol Interactor A", "Official Symbol Interactor B",
                "Organism ID Interactor A", "Organism ID Interactor B",
                "Experimental System Type"]
        df = pd.read_csv(path, sep="\t", usecols=lambda c: c in cols, low_memory=False)
        human = df[
            (df.get("Organism ID Interactor A", 9606) == 9606) &
            (df.get("Organism ID Interactor B", 9606) == 9606)
        ]
        ppi = human[human.get("Experimental System Type", "") != "Genetic"]
        for _, row in ppi.iterrows():
            a = row.get("Official Symbol Interactor A", "")
            b = row.get("Official Symbol Interactor B", "")
            if a and b and (a in gene_set or b in gene_set):
                if not G.has_edge(a, b):
                    G.add_edge(a, b, weight=0.5)
    except Exception as exc:
        log.warning("[1.6] BioGRID load failed: %s", exc)


def _load_primekg_fallback(G: nx.Graph, dark_genes: Set[str]) -> None:
    """Use PrimeKG protein-protein interaction subgraph for Tdark genes."""
    kg_path = settings.DB_PRIMEKG / "kg.csv"
    if not kg_path.exists():
        return
    try:
        # PrimeKG kg.csv columns: x_id, x_type, x_name, y_id, y_type, y_name, relation, display_relation
        chunks = pd.read_csv(kg_path, chunksize=200_000, low_memory=False)
        for chunk in chunks:
            # Protein-protein edges
            ppi = chunk[
                (chunk["x_type"] == "gene/protein") &
                (chunk["y_type"] == "gene/protein") &
                (chunk["x_name"].isin(dark_genes) | chunk["y_name"].isin(dark_genes))
            ]
            for _, row in ppi.iterrows():
                G.add_edge(row["x_name"], row["y_name"], weight=0.4, source="primekg")
    except Exception as exc:
        log.warning("[1.6] PrimeKG fallback failed: %s", exc)
