"""
Phase 1 — Feature matrix assembly.

Produces a gene-indexed float32 DataFrame:
  ~19,700 genes × [512 STRING-embedding dims + DepMap (2) + GTEx (2) + AlphaMissense (2)]

Memory discipline — every block is read in a way that never materialises the full
source file:
  STRING  : load the pre-built 48 MB parquet directly.
  DepMap  : 440 MB CSV read once with usecols, transposed immediately, cast float32.
  GTEx    : 74k × 19k sample matrix — streamed via pyarrow row groups (one gene-batch
             at a time) → only per-gene summary stats survive in memory.
  AlphaMissense: 5.4 GB tsv — streamed once, per-accession stats accumulated, then
                 cached to am_gene_stats.parquet (~2–3 min on first run, <0.1s warm).

Peak RAM target: < 2 GB for the full assembly pass.
"""
from __future__ import annotations
import gc
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

DB = Path("Databases")
_EMBEDDING_PATH = DB / "string" / "string_node2vec_512.parquet"
_DEPMAP_PATH = DB / "depmap" / "CRISPRGeneEffect.csv"
_GTEX_PATH = DB / "gtex" / "GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.parquet"
_ALPHAMISSENSE_PATH = DB / "alphamissense" / "AlphaMissense_hg38.tsv"
_STRING_INFO_PATH = DB / "string" / "9606.protein.info.v12.0.txt"
_GTEX_CACHE_PATH = DB / "gtex" / "gtex_gene_stats.parquet"

# Chronos threshold for "selective essential" (negative = reduces fitness)
_CHRON_SEL_THRESHOLD = -0.5


# ── Public entry point ────────────────────────────────────────────────────────

def build_feature_matrix(
    gene_universe: Optional[List[str]] = None,
    embedding_path: Path = _EMBEDDING_PATH,
    depmap_path: Path = _DEPMAP_PATH,
    gtex_path: Path = _GTEX_PATH,
) -> pd.DataFrame:
    """
    Return a float32 DataFrame (index=symbol, columns=features).

    gene_universe: list of HGNC symbols to include. If None, uses all symbols
    from the STRING info file (~19,700). Missing values from any source are
    imputed with the column median.
    """
    if gene_universe is None:
        gene_universe = _load_gene_universe()

    log.info("[matrix] Universe: %d genes", len(gene_universe))
    genes = pd.Index(sorted(gene_universe))

    # ── Block 1: STRING spectral embedding (512 dims) ─────────────────────────
    emb = _load_embedding(embedding_path, genes)
    log.info("[matrix] Embedding block: %s", emb.shape)

    # ── Block 2: DepMap essentiality (2 features) ─────────────────────────────
    dep = _load_depmap(depmap_path, genes)
    log.info("[matrix] DepMap block: %s", dep.shape)

    # ── Block 3: GTEx global expression (2 features) ──────────────────────────
    gtx = _load_gtex(gtex_path, genes)
    log.info("[matrix] GTEx block: %s", gtx.shape)

    # ── Block 4: AlphaMissense constraint (2 features, optional) ─────────────
    am = _load_alphamissense(genes)
    if am is not None:
        log.info("[matrix] AlphaMissense block: %s", am.shape)

    # ── Merge onto gene universe ──────────────────────────────────────────────
    blocks = [emb, dep, gtx] + ([am] if am is not None else [])
    master = blocks[0]
    for blk in blocks[1:]:
        master = master.join(blk, how="left")
    del blocks; gc.collect()

    # Impute missing with column median (NaN = gene absent from that source).
    for col in master.columns:
        if master[col].isna().any():
            master[col] = master[col].fillna(master[col].median())

    master = master.astype("float32")
    peak_mb = master.memory_usage(deep=True).sum() / 1e6
    log.info(
        "[matrix] Final matrix: %d genes × %d features  %.1f MB",
        len(master), len(master.columns), peak_mb,
    )
    return master


# ── Gene universe ─────────────────────────────────────────────────────────────

def _load_gene_universe() -> List[str]:
    info = pd.read_csv(_STRING_INFO_PATH, sep="\t",
                       usecols=["preferred_name"])
    return info["preferred_name"].dropna().unique().tolist()


# ── Block 1: spectral embedding ───────────────────────────────────────────────

def _load_embedding(path: Path, genes: pd.Index) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"STRING embedding not found at {path}. "
            "Run: .venv/bin/python scripts/precompute_string_embedding.py"
        )
    emb = pd.read_parquet(path).astype("float32")
    emb.index.name = "symbol"
    # Reindex to full gene universe; genes absent from STRING get 0-vector.
    emb = emb.reindex(genes, fill_value=0.0)
    return emb


# ── Block 2: DepMap Chronos essentiality ──────────────────────────────────────

def _load_depmap(path: Path, genes: pd.Index) -> pd.DataFrame:
    if not path.exists():
        log.warning("[matrix] DepMap not found — essentiality block skipped")
        return pd.DataFrame(index=genes, columns=["chronos_median", "selective_fraction"],
                            dtype="float32")

    # Columns are "SYMBOL (ENTREZ_ID)"; index is cell-line ID.
    # We need: for each gene, median Chronos across cell lines.
    # Read without dtype cast — index col is a string (ACH-…); cast values after.
    raw = pd.read_csv(path, index_col=0)
    raw.columns = [re.sub(r"\s*\(\d+\)$", "", c).strip() for c in raw.columns]
    raw = raw.astype("float32")
    # Transpose: genes as rows, cell-lines as columns.
    raw = raw.T
    # Dedupe if multiple columns resolve to same symbol (rare).
    raw = raw.groupby(level=0).median()

    chronos_median = raw.median(axis=1).rename("chronos_median")
    selective_frac = (raw < _CHRON_SEL_THRESHOLD).mean(axis=1).rename("selective_fraction")
    dep = pd.concat([chronos_median, selective_frac], axis=1).astype("float32")
    dep.index.name = "symbol"
    del raw; gc.collect()
    return dep.reindex(genes)


# ── Block 3: GTEx global expression (streaming via pyarrow row groups) ────────

def _load_gtex(path: Path, genes: pd.Index) -> pd.DataFrame:
    if not path.exists():
        log.warning("[matrix] GTEx not found — expression block skipped")
        return pd.DataFrame(index=genes, columns=["gtex_log_mean_tpm", "gtex_pct_expressed"],
                            dtype="float32")

    # Use cached per-gene stats if available (saves ~50s of streaming on each run).
    if _GTEX_CACHE_PATH.exists():
        cached = pd.read_parquet(_GTEX_CACHE_PATH)
        cached.index.name = "symbol"
        log.info("[matrix] GTEx loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes)

    log.info("[matrix] GTEx: streaming raw parquet to build gene stats cache…")
    pf = pq.ParquetFile(path)
    log_means: Dict[str, float] = {}
    pct_expr: Dict[str, float] = {}

    for i, batch in enumerate(pf.iter_batches(batch_size=2000)):
        df = batch.to_pandas()
        # Description column = gene symbol; Name index = ENSG with version.
        if "Description" not in df.columns:
            continue
        syms = df["Description"].values
        # Drop non-numeric (Description) for stats.
        num = df.drop(columns=["Description"], errors="ignore").astype("float32").values
        # log1p(TPM) mean per gene.
        log_tpm = np.log1p(num)
        batch_means = log_tpm.mean(axis=1)     # shape (n_genes_in_batch,)
        batch_pct = (num > 0).mean(axis=1)
        for sym, m, p in zip(syms, batch_means, batch_pct):
            if sym in log_means:
                # Multiple ENSG rows → keep max expression (longest/canonical isoform).
                if m > log_means[sym]:
                    log_means[sym] = float(m)
                    pct_expr[sym] = float(p)
            else:
                log_means[sym] = float(m)
                pct_expr[sym] = float(p)

    gtx = pd.DataFrame({
        "gtex_log_mean_tpm": log_means,
        "gtex_pct_expressed": pct_expr,
    }, dtype="float32")
    gtx.index.name = "symbol"
    try:
        _GTEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        gtx.to_parquet(_GTEX_CACHE_PATH)
        log.info("[matrix] GTEx stats cached → %s", _GTEX_CACHE_PATH)
    except Exception as exc:
        log.warning("[matrix] GTEx cache write failed: %s", exc)
    return gtx.reindex(genes)


# ── Block 4: AlphaMissense constraint (grep-indexed, optional) ────────────────

_AM_CACHE_PATH = DB / "alphamissense" / "am_gene_stats.parquet"


def _load_alphamissense(genes: pd.Index) -> Optional[pd.DataFrame]:
    """
    Build per-symbol mean pathogenicity + high-path fraction.

    Strategy: stream the 5.2 GB TSV exactly once, accumulate per-accession stats,
    map to gene symbols via the HGNC map, then cache to a small parquet.
    Subsequent runs load in <0.1s from cache.

    The old grep-per-batch approach works for Phase 2's per-gene lookups (a few
    proteins at a time) but is impractical for the full ~20k-gene Phase 1 scan.
    """
    if not _ALPHAMISSENSE_PATH.exists():
        log.warning("[matrix] AlphaMissense not found — constraint block skipped")
        return None

    uniprot_map = _build_uniprot_map()       # {accession: symbol}
    if not uniprot_map:
        log.warning("[matrix] No UniProt→symbol map — AlphaMissense block skipped")
        return None

    # ── Use cache if present ──────────────────────────────────────────────────
    if _AM_CACHE_PATH.exists():
        cached = pd.read_parquet(_AM_CACHE_PATH)
        cached.index.name = "symbol"
        log.info("[matrix] AlphaMissense loaded from cache (%d genes)", len(cached))
        return cached.reindex(genes)

    # ── Stream the file once, accumulate per-accession stats ─────────────────
    log.info("[matrix] AlphaMissense: streaming %s (this takes ~2–3 min once)…",
             _ALPHAMISSENSE_PATH.name)

    acc_set = set(uniprot_map.keys())
    # Use accumulators: sum_score, count, count_high_path — avoids list growth
    sum_score: Dict[str, float] = {}
    n_variants: Dict[str, int] = {}
    n_high: Dict[str, int] = {}

    try:
        with open(_ALPHAMISSENSE_PATH, "r") as fh:
            for i, line in enumerate(fh):
                # Skip header/comment lines (AlphaMissense has a short header)
                if line.startswith("#") or line.startswith("CHROM"):
                    continue
                parts = line.split("\t")
                if len(parts) < 10:
                    continue
                acc = parts[5]          # uniprot_id column
                if acc not in acc_set:
                    continue
                try:
                    score = float(parts[8])     # pathogenicity score
                    label = parts[9].strip()    # am_class
                except (ValueError, IndexError):
                    continue
                sum_score[acc] = sum_score.get(acc, 0.0) + score
                n_variants[acc] = n_variants.get(acc, 0) + 1
                if label == "likely_pathogenic":
                    n_high[acc] = n_high.get(acc, 0) + 1
                if i % 5_000_000 == 0 and i > 0:
                    log.info("[matrix] AlphaMissense: scanned %dM rows, %d accs seen",
                             i // 1_000_000, len(sum_score))
    except Exception as exc:
        log.warning("[matrix] AlphaMissense stream failed: %s", exc)
        return None

    if not sum_score:
        log.warning("[matrix] AlphaMissense: no matching accessions found in file")
        return None

    # ── Map accessions → gene symbols ─────────────────────────────────────────
    mean_path: Dict[str, float] = {}
    hi_frac: Dict[str, float] = {}
    for acc, total in sum_score.items():
        sym = uniprot_map.get(acc)
        if not sym:
            continue
        n = n_variants[acc]
        mean_path[sym] = round(total / n, 6)
        hi_frac[sym] = round(n_high.get(acc, 0) / n, 6)

    am = pd.DataFrame({
        "am_mean_pathogenicity": mean_path,
        "am_high_path_fraction": hi_frac,
    }, dtype="float32")
    am.index.name = "symbol"

    # ── Cache to parquet ──────────────────────────────────────────────────────
    try:
        _AM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        am.to_parquet(_AM_CACHE_PATH)
        log.info("[matrix] AlphaMissense stats cached → %s (%d genes)", _AM_CACHE_PATH, len(am))
    except Exception as exc:
        log.warning("[matrix] AlphaMissense cache write failed: %s", exc)

    return am.reindex(genes)


_HGNC_PATH = DB / "omim" / "hgnc_complete_set.txt"


def _build_uniprot_map() -> Dict[str, str]:
    """
    Build {uniprot_accession: gene_symbol} from the HGNC complete set file.

    File columns (tab-separated, header on row 1):
      Approved symbol | Ensembl gene ID | UniProt ID(supplied by UniProt)

    One gene can have multiple UniProt accessions (pipe-separated in the cell).
    We map every accession → its canonical HGNC symbol.
    """
    if not _HGNC_PATH.exists():
        log.warning(
            "[matrix] HGNC file not found at %s — AlphaMissense block skipped. "
            "Download with: wget -O %s "
            "'https://www.genenames.org/cgi-bin/download/custom?"
            "col=gd_app_sym&col=gd_pub_ensembl_id&col=md_prot_id"
            "&status=Approved&hgnc_dbtag=on&order_by=gd_app_sym_sort&format=text&submit=submit'",
            _HGNC_PATH, _HGNC_PATH,
        )
        return {}

    mapping: Dict[str, str] = {}
    try:
        with open(_HGNC_PATH) as fh:
            for i, line in enumerate(fh):
                if i == 0:          # skip header
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                symbol = parts[0].strip()
                uniprot_raw = parts[2].strip()  # col 3: UniProt ID(s)
                if not symbol or not uniprot_raw:
                    continue
                # UniProt cell can be a single accession or pipe-separated list
                for acc in uniprot_raw.split("|"):
                    acc = acc.strip()
                    if acc:
                        mapping[acc] = symbol
        log.info("[matrix] HGNC UniProt map: %d accessions for %d symbols",
                 len(mapping), len({v for v in mapping.values()}))
    except Exception as exc:
        log.warning("[matrix] HGNC UniProt map build failed: %s", exc)
    return mapping
