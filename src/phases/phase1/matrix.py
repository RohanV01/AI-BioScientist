"""
Phase 1 — Feature matrix assembly (revised 2026-06-01).

Previous design used a 512-d STRING Node2Vec embedding as the dominant
feature block. That embedding was built on STRING combined_score which has
textmining as its strongest component (r=0.662 vs combined_score), so the
model was doing literature-proximity lookup — the opposite of what was intended.

New design: 16 explicit, interpretable features.
  Network (literature-blind, only experimental/curated/coexpression channels):
    string_exp_degree      STRING experimental channel degree     (log1p)
    string_db_degree       STRING curated-database channel degree  (log1p)
    string_coexp_degree    STRING coexpression channel degree      (log1p)
    biogrid_degree         BioGRID physical PPI degree             (log1p)
    primekg_disease_degree # disease nodes connected in PrimeKG    (log1p, hub proxy)
    primekg_pathway_degree # pathway nodes connected in PrimeKG    (log1p)

  Functional genomics:
    essentiality           DepMap Chronos median across cell lines (raw)
    selectivity            fraction of cell lines where essential  (raw)
    expression             GTEx log1p(mean TPM) across tissues     (raw)
    pct_expressed          fraction of GTEx samples expressing gene(raw)
    am_pathogenicity       AlphaMissense mean variant pathogenicity(raw)
    am_high_path_frac      fraction of missense variants pathogenic(raw)

  Clinical precedent:
    chembl_max_phase       highest clinical phase of any drug (0–1, /4)
    is_mendelian           OMIM mim2gene.txt gene-type entry   (binary)

  Disease-specific (injected per run after OT pull in step 1.2):
    ot_genetic_assoc       OT integrated genetic association score (0–1)
    ot_tractability        OT tractability score                   (0–1)

All disease-agnostic blocks are cached to parquet on first run (<0.1s warm).
Peak RAM: < 500 MB total.
"""
from __future__ import annotations
import gc
import logging
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

DB = Path("Databases")

# Source files
_STRING_INFO_PATH     = DB / "string" / "9606.protein.info.v12.0.txt"
_STRING_LINKS_PATH    = DB / "string" / "9606.protein.links.detailed.v12.0.txt"
_BIOGRID_PATH         = DB / "biogrid" / "BIOGRID-ORGANISM-Homo_sapiens-5.0.257.tab3.txt"
_PRIMEKG_PATH         = DB / "primekg" / "kg.csv"
_CHEMBL_PATH          = DB / "chembl" / "chembl_37.db"
_OMIM_PATH            = DB / "omim" / "mim2gene.txt"
_HGNC_PATH            = DB / "omim" / "hgnc_complete_set.txt"
_DEPMAP_PATH          = DB / "depmap" / "CRISPRGeneEffect.csv"
_GTEX_PATH            = DB / "gtex" / "GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.parquet"
_ALPHAMISSENSE_PATH   = DB / "alphamissense" / "AlphaMissense_hg38.tsv"

# Cache files (precomputed on first run)
_STRING_CHANNELS_CACHE = DB / "string" / "string_channel_degrees.parquet"
_BIOGRID_CACHE         = DB / "biogrid" / "biogrid_physical_degree.parquet"
_PRIMEKG_CACHE         = DB / "primekg" / "primekg_gene_degrees.parquet"
_CHEMBL_CACHE          = DB / "chembl" / "chembl_gene_maxphase.parquet"
_GTEX_CACHE_PATH       = DB / "gtex" / "gtex_gene_stats.parquet"
_AM_CACHE_PATH         = DB / "alphamissense" / "am_gene_stats.parquet"
_STRING_DEGREE_CACHE   = DB / "string" / "string_degree_centrality.parquet"

# Minimum score threshold for each STRING channel to count an edge as real evidence
_STRING_CHANNEL_THRESHOLD = 200


# ── Public API ────────────────────────────────────────────────────────────────

def build_feature_matrix(
    gene_universe: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Return a float32 DataFrame (index=gene_symbol, columns=14 features).

    All 14 features are disease-agnostic — they describe the gene's biology
    independently of any specific disease context.  Disease-specific signals
    (OT genetic association, tractability) are kept out of the training matrix
    so the PU model learns a pure biological fingerprint.  Those signals are
    stored separately in the evidence trail for Phase 2 to consume.

    Missing values are imputed with 0.0 ("no evidence" is the correct default).
    """
    if gene_universe is None:
        gene_universe = _load_gene_universe()

    log.info("[matrix] Universe: %d genes", len(gene_universe))
    genes = pd.Index(sorted(gene_universe))

    # ── Block 1: STRING channel degrees (literature-blind) ────────────────────
    net = _load_string_channels(genes)
    log.info("[matrix] STRING channels: %s", net.shape)

    # ── Block 2: BioGRID physical degree ──────────────────────────────────────
    bg = _load_biogrid_degree(genes)
    log.info("[matrix] BioGRID: %s", bg.shape)

    # ── Block 3: PrimeKG disease + pathway degrees ────────────────────────────
    pkg = _load_primekg_degrees(genes)
    log.info("[matrix] PrimeKG: %s", pkg.shape)

    # ── Block 4: DepMap essentiality ──────────────────────────────────────────
    dep = _load_depmap(genes)
    log.info("[matrix] DepMap: %s", dep.shape)

    # ── Block 5: GTEx expression ──────────────────────────────────────────────
    gtx = _load_gtex(genes)
    log.info("[matrix] GTEx: %s", gtx.shape)

    # ── Block 6: AlphaMissense constraint ─────────────────────────────────────
    am = _load_alphamissense(genes)
    if am is not None:
        log.info("[matrix] AlphaMissense: %s", am.shape)

    # ── Block 7: ChEMBL clinical precedent ────────────────────────────────────
    chm = _load_chembl_maxphase(genes)
    log.info("[matrix] ChEMBL: %s", chm.shape)

    # ── Block 8: OMIM Mendelian flag ──────────────────────────────────────────
    omim = _load_omim_mendelian(genes)
    log.info("[matrix] OMIM: %s", omim.shape)

    # ── Merge all 14 disease-agnostic blocks ──────────────────────────────────
    blocks = [net, bg, pkg, dep, gtx, omim, chm]
    if am is not None:
        blocks.append(am)
    master = blocks[0]
    for blk in blocks[1:]:
        master = master.join(blk, how="left")
    del blocks; gc.collect()

    master = master.fillna(0.0).astype("float32")

    peak_mb = master.memory_usage(deep=True).sum() / 1e6
    log.info(
        "[matrix] Final matrix: %d genes × %d features  %.1f MB",
        len(master), len(master.columns), peak_mb,
    )
    return master


def load_string_degree() -> "pd.Series":
    """
    High-confidence (combined_score ≥ 700) STRING degree per gene.
    Used for ppi_eigenvector compat key in evidence_trail; not a matrix feature.
    Cached to _STRING_DEGREE_CACHE.
    """
    if _STRING_DEGREE_CACHE.exists():
        cached = pd.read_parquet(_STRING_DEGREE_CACHE)
        log.info("[matrix] STRING degree loaded from cache (%d genes)", len(cached))
        return cached["degree"]

    if not _STRING_LINKS_PATH.exists():
        raise FileNotFoundError(f"STRING links not found at {_STRING_LINKS_PATH}")

    info = pd.read_csv(_STRING_INFO_PATH, sep="\t",
                       usecols=["#string_protein_id", "preferred_name"])
    info.columns = ["protein_id", "symbol"]
    prot2sym: Dict[str, str] = dict(zip(info["protein_id"], info["symbol"]))
    del info

    log.info("[matrix] STRING degree: streaming links (score ≥ 700)…")
    degree: Counter = Counter()
    for chunk in pd.read_csv(_STRING_LINKS_PATH, sep=" ",
                             usecols=["protein1", "protein2", "combined_score"],
                             chunksize=500_000, dtype={"combined_score": "int32"}):
        hi = chunk[chunk["combined_score"] >= 700]
        degree.update(hi["protein1"].values)
        degree.update(hi["protein2"].values)

    gene_degree: Dict[str, int] = {}
    for pid, deg in degree.items():
        sym = prot2sym.get(pid)
        if sym:
            gene_degree[sym] = gene_degree.get(sym, 0) + deg

    result = pd.DataFrame({"degree": gene_degree}, dtype="float32")
    result.index.name = "symbol"
    try:
        _STRING_DEGREE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_STRING_DEGREE_CACHE)
        log.info("[matrix] STRING degree cached → %s", _STRING_DEGREE_CACHE)
    except Exception as exc:
        log.warning("[matrix] STRING degree cache write failed: %s", exc)
    return result["degree"]


# ── Gene universe ─────────────────────────────────────────────────────────────

def _load_gene_universe() -> List[str]:
    info = pd.read_csv(_STRING_INFO_PATH, sep="\t", usecols=["preferred_name"])
    return info["preferred_name"].dropna().unique().tolist()


# ── Block 1: STRING channel degrees ──────────────────────────────────────────

def _load_string_channels(genes: pd.Index) -> pd.DataFrame:
    """
    Per-gene degree in three literature-blind STRING channels.
    Edges counted only when channel score >= _STRING_CHANNEL_THRESHOLD (200).
    Textmining and cooccurence channels are deliberately excluded.
    """
    if _STRING_CHANNELS_CACHE.exists():
        cached = pd.read_parquet(_STRING_CHANNELS_CACHE)
        cached.index.name = "symbol"
        log.info("[matrix] STRING channels loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    if not _STRING_LINKS_PATH.exists():
        log.warning("[matrix] STRING links not found — channel degree block skipped")
        return pd.DataFrame(0.0, index=genes,
                            columns=["string_exp_degree", "string_db_degree", "string_coexp_degree"],
                            dtype="float32")

    info = pd.read_csv(_STRING_INFO_PATH, sep="\t",
                       usecols=["#string_protein_id", "preferred_name"])
    info.columns = ["protein_id", "symbol"]
    prot2sym: Dict[str, str] = dict(zip(info["protein_id"], info["symbol"]))
    del info

    log.info("[matrix] STRING channels: streaming links (channel threshold=%d)…",
             _STRING_CHANNEL_THRESHOLD)
    thr = _STRING_CHANNEL_THRESHOLD
    exp_deg:   Counter = Counter()
    db_deg:    Counter = Counter()
    coexp_deg: Counter = Counter()

    for chunk in pd.read_csv(
        _STRING_LINKS_PATH, sep=" ",
        usecols=["protein1", "protein2", "experimental", "database", "coexpression"],
        chunksize=500_000,
        dtype={"experimental": "int32", "database": "int32", "coexpression": "int32"},
    ):
        for col, counter in [
            ("experimental", exp_deg),
            ("database",     db_deg),
            ("coexpression", coexp_deg),
        ]:
            hi = chunk[chunk[col] >= thr]
            counter.update(hi["protein1"].values)
            counter.update(hi["protein2"].values)

    def _to_gene_series(counter: Counter, name: str) -> pd.Series:
        gene_counts: Dict[str, float] = {}
        for pid, cnt in counter.items():
            sym = prot2sym.get(pid)
            if sym:
                gene_counts[sym] = gene_counts.get(sym, 0.0) + cnt
        s = pd.Series(gene_counts, dtype="float32", name=name)
        return np.log1p(s)

    result = pd.concat([
        _to_gene_series(exp_deg,   "string_exp_degree"),
        _to_gene_series(db_deg,    "string_db_degree"),
        _to_gene_series(coexp_deg, "string_coexp_degree"),
    ], axis=1).fillna(0.0).astype("float32")
    result.index.name = "symbol"

    try:
        _STRING_CHANNELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_STRING_CHANNELS_CACHE)
        log.info("[matrix] STRING channels cached → %s (%d genes)", _STRING_CHANNELS_CACHE, len(result))
    except Exception as exc:
        log.warning("[matrix] STRING channels cache write failed: %s", exc)

    return result.reindex(genes, fill_value=0.0)


# ── Block 2: BioGRID physical degree ─────────────────────────────────────────

def _load_biogrid_degree(genes: pd.Index) -> pd.DataFrame:
    if _BIOGRID_CACHE.exists():
        cached = pd.read_parquet(_BIOGRID_CACHE)
        cached.index.name = "symbol"
        log.info("[matrix] BioGRID loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    if not _BIOGRID_PATH.exists():
        log.warning("[matrix] BioGRID not found — biogrid_degree block skipped")
        return pd.DataFrame(0.0, index=genes, columns=["biogrid_degree"], dtype="float32")

    log.info("[matrix] BioGRID: loading physical interactions…")
    bg = pd.read_csv(
        _BIOGRID_PATH, sep="\t", low_memory=False,
        usecols=["Official Symbol Interactor A", "Official Symbol Interactor B",
                 "Experimental System Type"],
    )
    physical = bg[bg["Experimental System Type"] == "physical"]
    all_syms = pd.concat([
        physical["Official Symbol Interactor A"],
        physical["Official Symbol Interactor B"],
    ])
    degree = np.log1p(all_syms.value_counts()).rename("biogrid_degree").astype("float32")
    result = degree.to_frame()
    result.index.name = "symbol"

    try:
        _BIOGRID_CACHE.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_BIOGRID_CACHE)
        log.info("[matrix] BioGRID cached → %s (%d genes)", _BIOGRID_CACHE, len(result))
    except Exception as exc:
        log.warning("[matrix] BioGRID cache write failed: %s", exc)

    return result.reindex(genes, fill_value=0.0)


# ── Block 3: PrimeKG disease + pathway degrees ────────────────────────────────

def _load_primekg_degrees(genes: pd.Index) -> pd.DataFrame:
    if _PRIMEKG_CACHE.exists():
        cached = pd.read_parquet(_PRIMEKG_CACHE)
        cached.index.name = "symbol"
        log.info("[matrix] PrimeKG loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    if not _PRIMEKG_PATH.exists():
        log.warning("[matrix] PrimeKG not found — primekg degree blocks skipped")
        return pd.DataFrame(0.0, index=genes,
                            columns=["primekg_disease_degree", "primekg_pathway_degree"],
                            dtype="float32")

    log.info("[matrix] PrimeKG: computing gene degree by relation type…")
    kg = pd.read_csv(_PRIMEKG_PATH,
                     usecols=["relation", "x_type", "x_name", "y_type", "y_name"])

    # disease_protein: genes connected to how many distinct disease nodes
    dp = kg[(kg["relation"] == "disease_protein") & (kg["y_type"] == "gene/protein")]
    disease_deg = np.log1p(
        dp.groupby("y_name")["x_name"].nunique()
    ).rename("primekg_disease_degree").astype("float32")

    # pathway_protein: genes connected to how many distinct pathway nodes
    pp = kg[(kg["relation"] == "pathway_protein") & (kg["y_type"] == "gene/protein")]
    pathway_deg = np.log1p(
        pp.groupby("y_name")["x_name"].nunique()
    ).rename("primekg_pathway_degree").astype("float32")

    result = pd.concat([disease_deg, pathway_deg], axis=1).fillna(0.0).astype("float32")
    result.index.name = "symbol"

    try:
        _PRIMEKG_CACHE.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_PRIMEKG_CACHE)
        log.info("[matrix] PrimeKG cached → %s (%d genes)", _PRIMEKG_CACHE, len(result))
    except Exception as exc:
        log.warning("[matrix] PrimeKG cache write failed: %s", exc)

    return result.reindex(genes, fill_value=0.0)


# ── Block 4: DepMap essentiality ──────────────────────────────────────────────

import re as _re
_CHRON_SEL_THRESHOLD = -0.5


def _load_depmap(genes: pd.Index) -> pd.DataFrame:
    if not _DEPMAP_PATH.exists():
        log.warning("[matrix] DepMap not found — essentiality block skipped")
        return pd.DataFrame(0.0, index=genes,
                            columns=["essentiality", "selectivity"], dtype="float32")

    raw = pd.read_csv(_DEPMAP_PATH, index_col=0)
    raw.columns = [_re.sub(r"\s*\(\d+\)$", "", c).strip() for c in raw.columns]
    raw = raw.astype("float32").T
    raw = raw.groupby(level=0).median()

    result = pd.concat([
        raw.median(axis=1).rename("essentiality"),
        (raw < _CHRON_SEL_THRESHOLD).mean(axis=1).rename("selectivity"),
    ], axis=1).astype("float32")
    result.index.name = "symbol"
    del raw; gc.collect()
    return result.reindex(genes, fill_value=0.0)


# ── Block 5: GTEx expression ──────────────────────────────────────────────────

def _load_gtex(genes: pd.Index) -> pd.DataFrame:
    if not _GTEX_PATH.exists():
        log.warning("[matrix] GTEx not found — expression block skipped")
        return pd.DataFrame(0.0, index=genes,
                            columns=["expression", "pct_expressed"], dtype="float32")

    if _GTEX_CACHE_PATH.exists():
        cached = pd.read_parquet(_GTEX_CACHE_PATH)
        cached.index.name = "symbol"
        log.info("[matrix] GTEx loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    log.info("[matrix] GTEx: streaming parquet to build cache…")
    pf = pq.ParquetFile(_GTEX_PATH)
    log_means: Dict[str, float] = {}
    pct_expr:  Dict[str, float] = {}

    for batch in pf.iter_batches(batch_size=2000):
        df = batch.to_pandas()
        if "Description" not in df.columns:
            continue
        syms = df["Description"].values
        num = df.drop(columns=["Description"], errors="ignore").astype("float32").values
        log_tpm = np.log1p(num)
        for sym, m, p in zip(syms, log_tpm.mean(axis=1), (num > 0).mean(axis=1)):
            if sym not in log_means or m > log_means[sym]:
                log_means[sym] = float(m)
                pct_expr[sym] = float(p)

    result = pd.DataFrame({
        "expression":    log_means,
        "pct_expressed": pct_expr,
    }, dtype="float32")
    result.index.name = "symbol"
    try:
        _GTEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_GTEX_CACHE_PATH)
    except Exception as exc:
        log.warning("[matrix] GTEx cache write failed: %s", exc)
    return result.reindex(genes, fill_value=0.0)


# ── Block 6: AlphaMissense constraint ────────────────────────────────────────

def _load_alphamissense(genes: pd.Index) -> Optional[pd.DataFrame]:
    if not _ALPHAMISSENSE_PATH.exists():
        log.warning("[matrix] AlphaMissense not found — constraint block skipped")
        return None

    uniprot_map = _build_uniprot_map()
    if not uniprot_map:
        log.warning("[matrix] No UniProt→symbol map — AlphaMissense block skipped")
        return None

    if _AM_CACHE_PATH.exists():
        cached = pd.read_parquet(_AM_CACHE_PATH)
        cached.index.name = "symbol"
        log.info("[matrix] AlphaMissense loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    log.info("[matrix] AlphaMissense: streaming (takes ~2–3 min once)…")
    acc_set = set(uniprot_map.keys())
    sum_score: Dict[str, float] = {}
    n_variants: Dict[str, int] = {}
    n_high: Dict[str, int] = {}

    try:
        with open(_ALPHAMISSENSE_PATH, "r") as fh:
            for i, line in enumerate(fh):
                if line.startswith("#") or line.startswith("CHROM"):
                    continue
                parts = line.split("\t")
                if len(parts) < 10:
                    continue
                acc = parts[5]
                if acc not in acc_set:
                    continue
                try:
                    score = float(parts[8])
                    label = parts[9].strip()
                except (ValueError, IndexError):
                    continue
                sum_score[acc] = sum_score.get(acc, 0.0) + score
                n_variants[acc] = n_variants.get(acc, 0) + 1
                if label == "likely_pathogenic":
                    n_high[acc] = n_high.get(acc, 0) + 1
    except Exception as exc:
        log.warning("[matrix] AlphaMissense stream failed: %s", exc)
        return None

    mean_path: Dict[str, float] = {}
    hi_frac:   Dict[str, float] = {}
    for acc, total in sum_score.items():
        sym = uniprot_map.get(acc)
        if not sym:
            continue
        n = n_variants[acc]
        mean_path[sym] = round(total / n, 6)
        hi_frac[sym]   = round(n_high.get(acc, 0) / n, 6)

    result = pd.DataFrame({
        "am_pathogenicity":  mean_path,
        "am_high_path_frac": hi_frac,
    }, dtype="float32")
    result.index.name = "symbol"
    try:
        _AM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_AM_CACHE_PATH)
        log.info("[matrix] AlphaMissense cached → %s (%d genes)", _AM_CACHE_PATH, len(result))
    except Exception as exc:
        log.warning("[matrix] AlphaMissense cache write failed: %s", exc)
    return result.reindex(genes, fill_value=0.0)


# ── Block 7: ChEMBL max clinical phase ───────────────────────────────────────

def _load_chembl_maxphase(genes: pd.Index) -> pd.DataFrame:
    if _CHEMBL_CACHE.exists():
        cached = pd.read_parquet(_CHEMBL_CACHE)
        cached.index.name = "symbol"
        log.info("[matrix] ChEMBL loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes, fill_value=0.0)

    if not _CHEMBL_PATH.exists():
        log.warning("[matrix] ChEMBL not found — chembl_max_phase block skipped")
        return pd.DataFrame(0.0, index=genes, columns=["chembl_max_phase"], dtype="float32")

    log.info("[matrix] ChEMBL: querying max_phase per human gene target…")
    try:
        conn = sqlite3.connect(_CHEMBL_PATH)
        df = pd.read_sql("""
            SELECT cs.component_synonym AS gene,
                   MAX(md.max_phase)    AS max_phase
            FROM   drug_mechanism    dm
            JOIN   target_components tc ON dm.tid = tc.tid
            JOIN   component_synonyms cs
                   ON tc.component_id = cs.component_id
                   AND cs.syn_type = 'GENE_SYMBOL'
            JOIN   molecule_dictionary md ON dm.molregno = md.molregno
            JOIN   target_dictionary  td ON dm.tid = td.tid
            WHERE  td.organism = 'Homo sapiens'
              AND  md.max_phase IS NOT NULL
            GROUP  BY cs.component_synonym
        """, conn)
        conn.close()
    except Exception as exc:
        log.warning("[matrix] ChEMBL query failed: %s", exc)
        return pd.DataFrame(0.0, index=genes, columns=["chembl_max_phase"], dtype="float32")

    df = df.dropna(subset=["max_phase"])
    df["gene"] = df["gene"].str.strip()
    # Deduplicate — take max phase per gene symbol
    df = df.groupby("gene")["max_phase"].max().reset_index()
    # Normalise 0–1 (approved drug = 1.0)
    df["chembl_max_phase"] = (df["max_phase"] / 4.0).clip(0.0, 1.0).astype("float32")
    result = df.set_index("gene")[["chembl_max_phase"]]
    result.index.name = "symbol"

    try:
        _CHEMBL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(_CHEMBL_CACHE)
        log.info("[matrix] ChEMBL cached → %s (%d genes)", _CHEMBL_CACHE, len(result))
    except Exception as exc:
        log.warning("[matrix] ChEMBL cache write failed: %s", exc)

    return result.reindex(genes, fill_value=0.0)


# ── Block 8: OMIM Mendelian gene flag ─────────────────────────────────────────

def _load_omim_mendelian(genes: pd.Index) -> pd.DataFrame:
    mendelian: set = set()
    if _OMIM_PATH.exists():
        try:
            with open(_OMIM_PATH) as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 4 and parts[1].strip() == "gene":
                        mendelian.add(parts[3].strip())
        except Exception as exc:
            log.warning("[matrix] OMIM parse failed: %s", exc)
    else:
        log.warning("[matrix] OMIM mim2gene.txt not found — is_mendelian = 0 for all")

    result = pd.DataFrame(
        {"is_mendelian": pd.Series(
            {g: 1.0 for g in genes if g in mendelian}, dtype="float32"
        )},
    ).reindex(genes, fill_value=0.0)
    result.index.name = "symbol"
    log.info("[matrix] OMIM: %d Mendelian genes flagged", int(result["is_mendelian"].sum()))
    return result


# ── UniProt→symbol map (for AlphaMissense) ───────────────────────────────────

def _build_uniprot_map() -> Dict[str, str]:
    if not _HGNC_PATH.exists():
        log.warning("[matrix] HGNC file not found — AlphaMissense block skipped")
        return {}
    mapping: Dict[str, str] = {}
    try:
        with open(_HGNC_PATH) as fh:
            for i, line in enumerate(fh):
                if i == 0:
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                symbol = parts[0].strip()
                for acc in parts[2].strip().split("|"):
                    acc = acc.strip()
                    if acc:
                        mapping[acc] = symbol
    except Exception as exc:
        log.warning("[matrix] HGNC UniProt map build failed: %s", exc)
    return mapping
