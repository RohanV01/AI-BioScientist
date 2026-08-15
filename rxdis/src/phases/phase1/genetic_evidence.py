"""
Phase 1.6 — Genetic evidence: GWAS Catalog + OMIM + Jensen Lab DISEASES.

Sources (in order of signal quality):
  1. GWAS Catalog  — local year-split TSVs (669 MB on disk, no API)
  2. OMIM          — local mim2gene.txt (Mendelian disease genes, no API)
  3. Jensen DISEASES — local TSVs, three tiers:
       knowledge_filtered   = manual curation   (highest confidence)
       experiments_filtered = experimental GWAS (medium)
       textmining_filtered  = literature mining  (broadest coverage)

DisGeNET removed 2026-05-31 (rate limit 10/day on free tier; replaced by
Jensen DISEASES which is unlimited, local-only, and updated weekly).
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List

import httpx
import pandas as pd

from src.config import settings

log = logging.getLogger(__name__)

_GWAS_CATALOG_REST = "https://www.ebi.ac.uk/gwas/rest/api/associations/search"
_DISEASES_DIR = Path("Databases/diseases_jensen")


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def get_gwas_evidence(
    efo_id: str,
    disease_name: str,
    mondo_ids: List[str] = None,
) -> Dict[str, Dict]:
    """
    Pull GWAS associations for the disease.
    Tries the local year-split TSV files first; falls back to the REST API.
    mondo_ids — MONDO cross-refs from OT (e.g. ["MONDO:0005192"]) used to search
    MAPPED_TRAIT_URI alongside the EFO ID (GWAS Catalog uses MONDO for many cancers).
    Returns {gene_symbol: {genetic_score, gwas_p, gwas_effect, force_include}}.
    """
    assoc_files = sorted(settings.DB_GWAS.glob("*associations*.tsv"))
    if assoc_files:
        merged: Dict[str, Dict] = {}
        for f in assoc_files:
            partial = _parse_gwas_local(f, efo_id, disease_name, mondo_ids=mondo_ids)
            for gene, data in partial.items():
                if data.get("genetic_score", 0) > merged.get(gene, {}).get("genetic_score", 0):
                    merged[gene] = data
        if merged:
            log.info("[1.6] GWAS local (%d files): %d genes total", len(assoc_files), len(merged))
            return merged
        log.info("[1.6] GWAS local files present but matched 0 rows — falling back to REST")

    return _gwas_rest(efo_id)


def get_omim_evidence(gene_symbols: List[str]) -> Dict[str, float]:
    """Returns {gene_symbol: omim_score} using the local mim2gene.txt."""
    result = _omim_local(gene_symbols)
    if not result and settings.OMIM_API_KEY:
        result = _omim_api(gene_symbols)
    return result



# Generic disease words that appear in many disease names — never use these alone as
# a match key because they would match far too broadly in the DISEASES database.
_GENERIC_DISEASE_WORDS = frozenset({
    "cancer", "disease", "syndrome", "disorder", "carcinoma", "tumor", "tumour",
    "neoplasm", "neoplasia", "malignancy", "malignant", "condition", "injury",
})


def _disease_specific_words(disease_name: str) -> frozenset:
    """Return words from disease_name that are specific enough to use as match keys."""
    return frozenset(
        w for w in disease_name.lower().split()
        if len(w) > 4 and w not in _GENERIC_DISEASE_WORDS
    )


def get_diseases_evidence(disease_name: str, doid_ids: List[str] = None) -> Dict[str, float]:
    """
    Jensen Lab DISEASES — query all three local TSV files.

    Match strategy:
      1. Exact disease-name substring: disease_key in dis_name
      2. Disease-specific word match: any specific word (>4 chars, not generic)
         from disease_name appears in dis_name — prevents short generic terms like
         "cancer" from matching entries for "pancreatic cancer".
      3. DOID ID match in col 3 (if doid_ids provided from OT cross-refs)

    Score conversion: DISEASES uses 1–5 stars.
      knowledge (curated): star × 0.20   → 0.20–1.00 (highest weight)
      experiments:         star × 0.15   → 0.15–0.75
      textmining:          score/10 capped at 0.60   (raw scores range 1–15+)

    Returns {gene_symbol: diseases_score}.
    """
    doid_set = set(doid_ids or [])
    disease_key = disease_name.lower().strip()
    specific_words = _disease_specific_words(disease_key)

    all_scores: Dict[str, float] = {}

    FILE_CONFIGS = [
        # (filename, score_col_index, score_type, weight)
        ("human_disease_knowledge_filtered.tsv",    6, "stars",  0.20),
        ("human_disease_experiments_filtered.tsv",  6, "stars",  0.15),
        ("human_disease_textmining_filtered.tsv",   4, "zscore", 1.0),
    ]

    for fname, score_col, score_type, weight in FILE_CONFIGS:
        fpath = _DISEASES_DIR / fname
        if not fpath.exists():
            log.warning("[1.6] DISEASES file not found: %s", fname)
            continue
        n_hits = 0
        try:
            with open(fpath) as fh:
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) <= score_col:
                        continue
                    gene_sym = parts[1].strip()          # col 2: gene symbol
                    doid     = parts[2].strip()          # col 3: DOID
                    dis_name = parts[3].strip().lower()  # col 4: disease name

                    # Match by exact phrase OR disease-specific word OR DOID.
                    # IMPORTANT: do NOT use dis_name in disease_key — that matches
                    # any short generic term (e.g. "cancer") inside the disease name
                    # and pulls in tens of thousands of unrelated entries.
                    name_match = (
                        disease_key in dis_name
                        or (bool(specific_words) and any(w in dis_name for w in specific_words))
                    )
                    doid_match = bool(doid_set) and doid in doid_set
                    if not (name_match or doid_match):
                        continue

                    if not gene_sym or gene_sym in ("nan", "-", ""):
                        continue

                    try:
                        raw_score = float(parts[score_col])
                    except (ValueError, IndexError):
                        continue

                    if score_type == "stars":
                        score = min(1.0, raw_score * weight)
                    else:
                        score = min(0.60, raw_score / 10.0)

                    if score > all_scores.get(gene_sym, 0.0):
                        all_scores[gene_sym] = round(score, 4)
                    n_hits += 1
        except Exception as exc:
            log.warning("[1.6] DISEASES parse failed (%s): %s", fname, exc)

        if n_hits:
            log.info("[1.6] DISEASES %s: %d rows matched, %d genes",
                     fname.split("_")[2], n_hits, len(all_scores))

    if not all_scores:
        log.info("[1.6] DISEASES: no matches for '%s' (tried %d DOID ids)",
                 disease_name, len(doid_set))
    else:
        log.info("[1.6] DISEASES total: %d unique genes", len(all_scores))

    return all_scores


def merge_genetic_evidence(
    gwas: Dict[str, Dict],
    omim: Dict[str, float],
    diseases: Dict[str, float],
) -> Dict[str, Dict]:
    """Merge all genetic evidence sources into a per-gene dict."""
    all_genes = set(gwas) | set(omim) | set(diseases)
    merged = {}
    for gene in all_genes:
        g = gwas.get(gene, {})
        o = omim.get(gene, 0.0)
        d = diseases.get(gene, 0.0)
        gwas_score = g.get("genetic_score", 0.0)
        # GWAS p<5e-8 > OMIM Mendelian > Jensen DISEASES text-evidence
        combined = max(gwas_score, o * 0.8, d * 0.7)
        merged[gene] = {
            "genetic_score": round(combined, 4),
            "gwas_p": g.get("gwas_p"),
            "gwas_effect": g.get("gwas_effect"),
            "force_include": g.get("force_include", False),
            "omim_score": o,
            "diseases_score": d,
        }
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# GWAS internals
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_gwas_local(
    path: Path,
    efo_id: str,
    disease_name: str,
    mondo_ids: List[str] = None,
) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}
    efo_suffix = efo_id.split("_")[-1]
    # GWAS Catalog uses MONDO IDs in MAPPED_TRAIT_URI for most cancer entries
    # (e.g. MONDO_0005192 for pancreatic cancer) rather than EFO IDs.
    # Convert "MONDO:0005192" → "MONDO_0005192" for URI search.
    mondo_suffixes = [m.replace(":", "_").split("_")[-1] for m in (mondo_ids or [])]
    # Core disease keyword for DISEASE/TRAIT column (contains, not startswith)
    specific_words = _disease_specific_words(disease_name)
    disease_keyword = next(iter(specific_words), disease_name.lower().split()[0])
    try:
        chunks = pd.read_csv(path, sep="\t", chunksize=50_000, low_memory=False)
        for chunk in chunks:
            mask = pd.Series(False, index=chunk.index)
            if "MAPPED_TRAIT_URI" in chunk.columns:
                uris = chunk["MAPPED_TRAIT_URI"].fillna("")
                mask |= uris.str.contains(efo_id, case=False, regex=False)
                if len(efo_suffix) >= 5:
                    mask |= uris.str.contains(efo_suffix, case=False, regex=False)
                # Also search MONDO IDs (GWAS Catalog uses these for many traits)
                for msuffix in mondo_suffixes:
                    if len(msuffix) >= 5:
                        mask |= uris.str.contains(msuffix, case=False, regex=False)
            if "DISEASE/TRAIT" in chunk.columns:
                # Use contains with the disease-specific keyword (not startswith)
                # so "pancreatic cancer" matches "pancreatic carcinoma" etc.
                mask |= chunk["DISEASE/TRAIT"].fillna("").str.lower().str.contains(
                    disease_keyword, case=False, regex=False
                )
            sub = chunk[mask]
            for _, row in sub.iterrows():
                mapped  = str(row.get("MAPPED_GENE", "")).strip()
                reported = str(row.get("REPORTED GENE(S)", "")).strip()
                gene_sym = mapped if mapped and mapped not in ("nan", "-", "") else reported
                if not gene_sym or gene_sym in ("nan", "-", ""):
                    continue
                gene_sym = gene_sym.split(" - ")[0].strip()
                if not gene_sym or " " in gene_sym:
                    continue
                try:
                    p_val = float(str(row.get("P-VALUE", "1")).replace(" ", "") or "1")
                except (ValueError, TypeError):
                    p_val = 1.0
                try:
                    effect = abs(float(str(row.get("OR or BETA", "0")).replace(" ", "") or "0"))
                    if effect > 100:
                        effect = 0.0
                except (ValueError, TypeError):
                    effect = 0.0
                score = _gwas_score(p_val, effect)
                force = p_val < 5e-8 and effect > 0.1
                if score > results.get(gene_sym, {}).get("genetic_score", 0):
                    results[gene_sym] = {
                        "genetic_score": round(score, 4),
                        "gwas_p": p_val,
                        "gwas_effect": round(effect, 4),
                        "force_include": force,
                    }
    except Exception as exc:
        log.warning("[1.6] Local GWAS parse failed (%s): %s", path.name, exc)
    return results


def _gwas_rest(efo_id: str) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}
    try:
        resp = httpx.get(_GWAS_CATALOG_REST, params={"efoTrait": efo_id, "size": 500}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("_embedded", {}).get("associations", [])
        for assoc in data:
            for loci in assoc.get("loci", []):
                for gene_info in loci.get("authorReportedGenes", []):
                    gene_sym = gene_info.get("geneName", "").strip()
                    if not gene_sym:
                        continue
                    p_val  = float(assoc.get("pvalue", 1) or 1)
                    effect = abs(float(assoc.get("betaNum", 0) or assoc.get("orPerCopyNum", 1) or 1))
                    score  = _gwas_score(p_val, effect)
                    if score > results.get(gene_sym, {}).get("genetic_score", 0):
                        results[gene_sym] = {
                            "genetic_score": round(score, 4),
                            "gwas_p": p_val,
                            "gwas_effect": round(effect, 4),
                            "force_include": p_val < 5e-8 and effect > 0.1,
                        }
        log.info("[1.6] GWAS REST: %d genes", len(results))
    except Exception as exc:
        log.warning("[1.6] GWAS REST failed: %s", exc)
    return results


def _gwas_score(p_val: float, effect: float) -> float:
    import math
    if p_val <= 0:
        p_val = 1e-300
    p_score = min(1.0, max(0.0, (-math.log10(p_val) - 1) / 10))
    e_score = min(1.0, max(0.0, effect / 2.0))
    return round(0.6 * p_score + 0.4 * e_score, 4)


# ═══════════════════════════════════════════════════════════════════════════════
# OMIM internals
# ═══════════════════════════════════════════════════════════════════════════════

def _omim_local(gene_symbols: List[str]) -> Dict[str, float]:
    mim2gene = settings.DB_OMIM / "mim2gene.txt"
    if not mim2gene.exists():
        return {}
    gene_set = set(gene_symbols)
    results: Dict[str, float] = {}
    try:
        with open(mim2gene) as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 4:
                    continue
                if parts[1].strip() == "gene" and parts[3].strip() in gene_set:
                    # 0.1: mim2gene.txt confirms Mendelian gene but is disease-agnostic.
                    # Kept low so disease-specific GWAS/DISEASES scores always dominate.
                    results[parts[3].strip()] = 0.1
        log.info("[1.6] OMIM local: %d genes with evidence", len(results))
    except Exception as exc:
        log.warning("[1.6] OMIM local parse failed: %s", exc)
    return results


def _omim_api(gene_symbols: List[str]) -> Dict[str, float]:
    results: Dict[str, float] = {}
    for sym in gene_symbols:
        try:
            resp = httpx.get(
                "https://api.omim.org/api/geneMap/search",
                params={"search": sym, "apiKey": settings.OMIM_API_KEY,
                        "format": "json", "limit": 3},
                timeout=10,
            )
            resp.raise_for_status()
            entries = resp.json().get("omim", {}).get("searchResponse", {}).get("geneMapList", [])
            if entries:
                results[sym] = min(1.0, 0.3 + 0.1 * len(entries))
        except Exception:
            pass
    log.info("[1.6] OMIM API: %d genes", len(results))
    return results
