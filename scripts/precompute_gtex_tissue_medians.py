"""
One-time precompute: GTEx per-tissue median TPM parquet.

Produces  Databases/gtex/gtex_tissue_medians.parquet
  Index:   gene symbol
  Columns: one per GTEx tissue site detail (e.g. "Pancreas", "Heart - Left Ventricle")
  Values:  median TPM across all donors for that tissue

Run once after downloading the GTEx sample attributes file:
  wget -O Databases/gtex/GTEx_SampleAttributesDS.txt \\
    "https://storage.googleapis.com/adult-gtex/annotations/v10/metadata-files/GTEx_Analysis_v10_Annotations_SampleAttributesDS.txt"

Then run:
  python scripts/precompute_gtex_tissue_medians.py

Takes ~5 min on an SSD (loads a 10 GB matrix into RAM).
Peak RAM: ~8 GB.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT   = Path(__file__).parents[1]
TPM_PARQUET = REPO_ROOT / "Databases" / "gtex" / "GTEx_Analysis_2026-05-19_v11_RNASeQCv2.4.3_gene_tpm.parquet"
OUT_PARQUET = REPO_ROOT / "Databases" / "gtex" / "gtex_tissue_medians.parquet"

# Default sample attributes path — download as described above
DEFAULT_ATTRS = REPO_ROOT / "Databases" / "gtex" / "GTEx_SampleAttributesDS.txt"

# Download URL for sample attributes (GTEx v10 — compatible with v11 sample IDs)
ATTRS_URL = (
    "https://storage.googleapis.com/adult-gtex/annotations/v10/metadata-files/"
    "GTEx_Analysis_v10_Annotations_SampleAttributesDS.txt"
)


def download_attrs(dest: Path) -> None:
    import requests
    log.info("Downloading GTEx sample attributes → %s", dest)
    resp = requests.get(ATTRS_URL, timeout=120, stream=True)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    log.info("Downloaded %d bytes", dest.stat().st_size)


def load_sample_tissue_map(attrs_path: Path) -> dict[str, str]:
    """
    Parse the GTEx sample attributes file and return {sample_id: tissue_site_detail}.
    Relevant columns: SAMPID (sample ID), SMTSD (tissue site detail, e.g. "Pancreas").
    """
    log.info("Loading sample attributes from %s", attrs_path)
    df = pd.read_csv(attrs_path, sep="\t", usecols=["SAMPID", "SMTSD"], dtype=str)
    mapping = dict(zip(df["SAMPID"], df["SMTSD"]))
    log.info("Sample → tissue map: %d entries, %d unique tissues",
             len(mapping), len(set(mapping.values())))
    return mapping


def build_tissue_medians(tpm_parquet: Path, sample_tissue: dict[str, str]) -> pd.DataFrame:
    """
    Load the full TPM matrix and compute per-tissue median TPM per gene.

    Output: DataFrame  index=gene_symbol, columns=tissue_name, values=median_TPM
    """
    log.info("Loading TPM matrix from %s  (this may take a few minutes)…", tpm_parquet)
    tpm = pd.read_parquet(tpm_parquet)

    # Extract gene symbol from the "Description" column (present in GTEx parquet)
    if "Description" in tpm.columns:
        symbols = tpm["Description"].values
        tpm = tpm.drop(columns=["Description"])
    else:
        # Fall back to index (Ensembl ID)
        symbols = tpm.index.values

    # Retain only sample columns that have a tissue mapping
    known_samples = [c for c in tpm.columns if c in sample_tissue]
    missing = len(tpm.columns) - len(known_samples)
    if missing:
        log.warning("%d sample columns not in attributes file (will be dropped)", missing)
    tpm = tpm[known_samples]

    log.info("Computing per-tissue medians (%d genes × %d samples → N tissues)…",
             len(tpm), len(known_samples))

    # Group samples by tissue and compute median
    tissues = sorted(set(sample_tissue[s] for s in known_samples))
    result = {}
    for tissue in tissues:
        cols = [s for s in known_samples if sample_tissue[s] == tissue]
        result[tissue] = tpm[cols].median(axis=1).values

    out = pd.DataFrame(result, index=symbols)
    out.index.name = "symbol"
    log.info("Tissue medians: %d genes × %d tissues", len(out), len(out.columns))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute GTEx tissue median TPM parquet.")
    parser.add_argument("--attrs", type=Path, default=DEFAULT_ATTRS,
                        help="GTEx sample attributes TSV (auto-downloaded if missing)")
    parser.add_argument("--tpm", type=Path, default=TPM_PARQUET,
                        help="Full GTEx TPM parquet")
    parser.add_argument("--out", type=Path, default=OUT_PARQUET,
                        help="Output parquet path")
    parser.add_argument("--download", action="store_true",
                        help="Download sample attributes file if not present")
    args = parser.parse_args()

    if not args.tpm.exists():
        log.error("TPM parquet not found: %s", args.tpm)
        sys.exit(1)

    if not args.attrs.exists():
        if args.download:
            download_attrs(args.attrs)
        else:
            log.error(
                "Sample attributes file not found: %s\n"
                "Download it with:\n"
                "  python %s --download\n"
                "or manually:\n"
                "  wget -O %s '%s'",
                args.attrs, __file__, args.attrs, ATTRS_URL,
            )
            sys.exit(1)

    sample_tissue = load_sample_tissue_map(args.attrs)
    medians = build_tissue_medians(args.tpm, sample_tissue)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    medians.to_parquet(args.out)
    log.info("Saved → %s  (%d KB)", args.out, args.out.stat().st_size // 1024)
    log.info(
        "Sample tissues: %s …",
        ", ".join(list(medians.columns[:5])),
    )


if __name__ == "__main__":
    main()
