#!/usr/bin/env python
"""
One-time precompute: STRING PPI → 512-d gensim-free network embedding (NetMF/SVD).

Why not node2vec/pecanpy? gensim has no Python 3.14 wheel (its Cython core uses the
removed CPython `ob_digit` / old `_PyLong_AsByteArray` C API). node2vec is provably
equivalent to an implicit factorization of a PPMI/adjacency matrix (Qiu et al., "NetMF",
WSDM 2018), so we factorize the symmetric-normalized adjacency directly with a randomized
TruncatedSVD — fully Python-3.14-native (scipy + scikit-learn) and lower-RAM than node2vec
(no random-walk corpus held in memory).

Output: Databases/string/string_node2vec_512.parquet
        row index = HGNC symbol; columns emb_0..emb_(d-1); float32.
Run once; rebuild only if CONF_MIN or DIM changes.

Usage:  .venv/bin/python scripts/precompute_string_embedding.py
"""
from __future__ import annotations
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [precompute] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB = Path("Databases/string")
LINKS = DB / "9606.protein.links.detailed.v12.0.txt"
INFO = DB / "9606.protein.info.v12.0.txt"
OUT = DB / "string_node2vec_512.parquet"

CONF_MIN = 700          # combined_score floor (high-confidence edges only)
DIM = 512               # embedding dimensionality (per the architecture directive)
CHUNK = 2_000_000       # rows per read_csv chunk (bounds peak RAM on the 868 MB file)
SEED = 42               # reproducibility


def load_ensp_to_symbol() -> dict:
    info = pd.read_csv(INFO, sep="\t", usecols=["#string_protein_id", "preferred_name"])
    m = dict(zip(info["#string_protein_id"], info["preferred_name"]))
    log.info("Loaded %d ENSP→symbol mappings", len(m))
    return m


def load_edges(ensp2sym: dict) -> pd.DataFrame:
    kept, total = [], 0
    for chunk in pd.read_csv(
        LINKS, sep=" ",
        usecols=["protein1", "protein2", "combined_score"],
        dtype={"combined_score": "int16"}, chunksize=CHUNK,
    ):
        total += len(chunk)
        kept.append(chunk[chunk["combined_score"] >= CONF_MIN])
    edges = pd.concat(kept, ignore_index=True)
    log.info("STRING edges: %d total → %d at combined_score >= %d", total, len(edges), CONF_MIN)

    edges["s1"] = edges["protein1"].map(ensp2sym)
    edges["s2"] = edges["protein2"].map(ensp2sym)
    edges = edges.dropna(subset=["s1", "s2"])
    edges = edges[edges["s1"] != edges["s2"]]
    # Collapse isoform/duplicate symbol pairs → keep the strongest edge.
    edges = edges.groupby(["s1", "s2"], sort=False)["combined_score"].max().reset_index()
    log.info("Symbol-level edges (deduped): %d", len(edges))
    return edges


def build_embedding(edges: pd.DataFrame) -> pd.DataFrame:
    symbols = pd.Index(sorted(set(edges["s1"]) | set(edges["s2"])))
    idx = {s: i for i, s in enumerate(symbols)}
    n = len(symbols)
    log.info("Graph: %d nodes", n)

    r = edges["s1"].map(idx).to_numpy()
    c = edges["s2"].map(idx).to_numpy()
    w = edges["combined_score"].to_numpy(dtype=np.float32) / 1000.0

    # Symmetric sparse adjacency.
    A = sp.coo_matrix(
        (np.concatenate([w, w]), (np.concatenate([r, c]), np.concatenate([c, r]))),
        shape=(n, n), dtype=np.float32,
    ).tocsr()
    A.sum_duplicates()

    # Symmetric-normalized adjacency with self-loops: D^-1/2 (A + I) D^-1/2.
    A = A + sp.identity(n, dtype=np.float32, format="csr")
    deg = np.asarray(A.sum(axis=1)).ravel()
    dinv = (1.0 / np.sqrt(np.maximum(deg, 1e-12))).astype(np.float32)
    D = sp.diags(dinv)
    A_norm = (D @ A @ D).tocsr()

    dim = min(DIM, n - 1)
    log.info("Randomized TruncatedSVD → %d dims ...", dim)
    svd = TruncatedSVD(n_components=dim, random_state=SEED, n_iter=7)
    emb = svd.fit_transform(A_norm).astype(np.float32)   # U·Σ spectral embedding
    log.info("Explained variance (top %d): %.3f", dim, float(svd.explained_variance_ratio_.sum()))

    df = pd.DataFrame(emb, index=symbols, columns=[f"emb_{i}" for i in range(dim)])
    df.index.name = "symbol"
    return df


def main() -> int:
    t0 = time.monotonic()
    if not LINKS.exists() or not INFO.exists():
        log.error("Missing STRING inputs: %s / %s", LINKS, INFO)
        return 1
    ensp2sym = load_ensp_to_symbol()
    edges = load_edges(ensp2sym)
    df = build_embedding(edges)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT)
    log.info("Wrote %s  shape=%s  (%.1f MB)  in %.1fs",
             OUT, df.shape, OUT.stat().st_size / 1e6, time.monotonic() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
