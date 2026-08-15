"""
Phase 1.4 — Literature mining via map-reduce.
MAP: PubMed ESearch+EFetch + Europe PMC → chunk → LLM extraction → llm_chunks.
REDUCE: tree-merge (local) or single-pass (frontier).
"""
from __future__ import annotations
import json
import logging
import time
from typing import Dict, List, Optional

import httpx

from src.config import settings
from src.llm.provider import LLMProvider
from src.llm.mapreduce import map_reduce
from src.db.run_state import log_decision
from .schemas import (
    AbstractRelevance, LiteratureChunkOutput, LiteratureRecord
)

log = logging.getLogger(__name__)

_PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


# ── PubMed fetch ─────────────────────────────────────────────────────────────

def fetch_pubmed_abstracts(disease_name: str, max_results: int = 500) -> List[Dict]:
    """Fetch PubMed abstracts for the disease query."""
    query = (
        f'("{disease_name}"[Title/Abstract]) AND '
        f'(target[Title/Abstract] OR biomarker[Title/Abstract] OR '
        f'GWAS[Title/Abstract] OR knockout[Title/Abstract])'
    )
    params = {
        "db": "pubmed", "term": query, "retmax": max_results,
        "retmode": "json", "sort": "relevance",
    }
    if settings.NCBI_API_KEY:
        params["api_key"] = settings.NCBI_API_KEY

    try:
        resp = httpx.get(f"{_PUBMED_BASE}/esearch.fcgi", params=params, timeout=20)
        resp.raise_for_status()
        pmids = resp.json()["esearchresult"]["idlist"]
    except Exception as exc:
        log.warning("[1.4] PubMed ESearch failed: %s", exc)
        return []

    if not pmids:
        return []

    return _fetch_abstracts(pmids)


def _fetch_abstracts(pmids: List[str]) -> List[Dict]:
    abstracts = []
    for i in range(0, len(pmids), 200):
        batch = pmids[i : i + 200]
        params = {
            "db": "pubmed", "id": ",".join(batch),
            "rettype": "abstract", "retmode": "json",
        }
        if settings.NCBI_API_KEY:
            params["api_key"] = settings.NCBI_API_KEY
            time.sleep(0.1)   # 10 req/s with key
        else:
            time.sleep(0.34)  # 3 req/s without key

        try:
            resp = httpx.get(f"{_PUBMED_BASE}/efetch.fcgi", params=params, timeout=30)
            resp.raise_for_status()
            articles = resp.json().get("PubmedArticleSet", {}).get("PubmedArticle", [])
            if isinstance(articles, dict):
                articles = [articles]
            for art in articles:
                med = art.get("MedlineCitation", {})
                pmid = med.get("PMID", {}).get("#text", "")
                article = med.get("Article", {})
                title = article.get("ArticleTitle", "")
                abstract_texts = article.get("Abstract", {}).get("AbstractText", [])
                if isinstance(abstract_texts, str):
                    abstract = abstract_texts
                elif isinstance(abstract_texts, list):
                    abstract = " ".join(
                        t.get("#text", t) if isinstance(t, dict) else t
                        for t in abstract_texts
                    )
                else:
                    abstract = ""

                year_raw = (
                    med.get("DateCompleted", {}).get("Year")
                    or article.get("Journal", {}).get("JournalIssue", {})
                              .get("PubDate", {}).get("Year")
                )
                year = int(year_raw) if year_raw else None

                if abstract:
                    abstracts.append({"pmid": pmid, "title": title, "abstract": abstract, "year": year})
        except Exception as exc:
            log.warning("[1.4] EFetch batch %d failed: %s", i, exc)

    log.info("[1.4] Fetched %d abstracts from PubMed", len(abstracts))
    return abstracts


def fetch_europepmc(disease_name: str, max_results: int = 200) -> List[Dict]:
    """Supplement with Europe PMC open-access full text."""
    try:
        resp = httpx.get(
            f"{_EUROPEPMC_BASE}/search",
            params={
                "query": f'"{disease_name}" AND (target OR biomarker)',
                "resultType": "core",
                "pageSize": min(max_results, 200),
                "format": "json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("resultList", {}).get("result", [])
        abstracts = []
        for r in results:
            abstract = r.get("abstractText", "")
            if abstract:
                abstracts.append({
                    "pmid": r.get("pmid", r.get("id", "")),
                    "title": r.get("title", ""),
                    "abstract": abstract,
                    "year": r.get("pubYear"),
                })
        log.info("[1.4] Europe PMC returned %d abstracts", len(abstracts))
        return abstracts
    except Exception as exc:
        log.warning("[1.4] Europe PMC fetch failed: %s", exc)
        return []


# ── LLM gates ────────────────────────────────────────────────────────────────

def relevance_prefilter(abstracts: List[Dict], disease_name: str, provider: LLMProvider) -> List[Dict]:
    """Cheap per-abstract keep/skip gate (gate 1.4_relevance_prefilter)."""
    if provider.capabilities.quality_tier == "frontier":
        # Frontier: skip prefilter, trust the search results
        return abstracts

    kept = []
    for ab in abstracts:
        prompt = (
            f"Is this abstract relevant to identifying drug targets for '{disease_name}'? "
            f"Score 0-10 (0=irrelevant, 10=highly relevant) and decide keep/skip.\n\n"
            f"Title: {ab['title']}\nAbstract: {ab['abstract'][:800]}"
        )
        try:
            result = provider.complete(prompt, schema=AbstractRelevance, temperature=0.0, max_tokens=64)
            parsed = result.parsed or {}
            if parsed.get("keep", True) and parsed.get("score_0_10", 5) >= 4:
                kept.append(ab)
        except Exception:
            kept.append(ab)  # Keep on error

    log.info("[1.4] Relevance prefilter: %d → %d abstracts", len(abstracts), len(kept))
    return kept


def _map_prompt(chunk: List[Dict]) -> str:
    formatted = "\n---\n".join(
        f"PMID:{ab['pmid']} ({ab.get('year','')})\n{ab['title']}\n{ab['abstract'][:1500]}"
        for ab in chunk
    )
    return (
        "Extract all gene/protein targets mentioned as disease-relevant in these abstracts. "
        "For each gene, include the PMID, a supporting sentence, and a literature_score 0.0–1.0 "
        "(1.0 = strong causal evidence, 0.3 = correlative).\n\n"
        f"{formatted}"
    )


def _reduce_prompt(partials: List[Dict]) -> str:
    text = json.dumps(partials, indent=1)
    return (
        "Merge these gene-disease evidence records from multiple literature chunks. "
        "Deduplicate by gene_symbol, aggregate evidence lists (keep strongest 5 per gene), "
        "and max-pool literature_scores. Return one ranked list.\n\n"
        f"{text[:6000]}"
    )


def mine_literature(
    run_id: str,
    disease_name: str,
    abstracts: List[Dict],
    provider: LLMProvider,
    db,
) -> Dict[str, Dict]:
    """
    Run the full map-reduce literature extraction.
    Returns a dict keyed by gene_symbol with aggregated literature data.
    """
    if not abstracts:
        log.warning("[1.4] No abstracts to mine")
        return {}

    final = map_reduce(
        run_id=run_id,
        task="phase1_literature_extraction",
        items=abstracts,
        map_prompt_fn=_map_prompt,
        map_schema=LiteratureChunkOutput,
        reduce_prompt_fn=_reduce_prompt,
        reduce_schema=LiteratureChunkOutput,
        provider=provider,
        db=db,
        reduce_fanin=8,
        temperature=0.1,
    )

    records = final.get("records", [])
    lit_map = {}
    for rec in records:
        sym = rec.get("gene_symbol", "")
        if sym:
            lit_map[sym] = {
                "literature_score": rec.get("literature_score", 0),
                "evidence": rec.get("evidence", []),
            }

    log.info("[1.4] Literature map-reduce extracted %d genes", len(lit_map))
    return lit_map
