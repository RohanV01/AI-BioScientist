"""
Individual health-check functions for Phase 0.
Each returns a dict: {service, ok, latency_ms, detail}.
"""
from __future__ import annotations
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from src.config import settings

log = logging.getLogger(__name__)


# ── Database presence checks ─────────────────────────────────────────────────

def _db_check(name: str, path: Path, version_hint: str = "") -> Dict[str, Any]:
    if path.exists():
        size_mb = path.stat().st_size / 1_048_576
        return {"name": name, "present": True, "version": version_hint, "size_mb": round(size_mb, 1)}
    return {"name": name, "present": False, "version": None, "size_mb": 0}


def check_all_databases() -> list[Dict[str, Any]]:
    results = []

    # PrimeKG — accept either kg.csv or nodes.csv+edges.csv
    kg_combined = settings.DB_PRIMEKG / "kg.csv"
    kg_nodes = settings.DB_PRIMEKG / "nodes.csv"
    if kg_combined.exists():
        results.append({"name": "PrimeKG", "present": True, "version": "combined_kg.csv",
                        "size_mb": round(kg_combined.stat().st_size / 1_048_576, 1)})
    elif kg_nodes.exists():
        results.append(_db_check("PrimeKG", kg_nodes, "split nodes/edges"))
    else:
        results.append({"name": "PrimeKG", "present": False, "version": None, "size_mb": 0})

    # DepMap — accept either filename variant
    depmap_file = settings.DB_DEPMAP / "CRISPRGeneEffect.csv"
    if not depmap_file.exists():
        depmap_file = settings.DB_DEPMAP / "CRISPR_gene_effect.csv"
    results.append(_db_check("DepMap", depmap_file, "CRISPRGeneEffect"))

    # STRING
    string_file = settings.DB_STRING / "9606.protein.links.detailed.v12.0.txt"
    if not string_file.exists():
        string_file = settings.DB_STRING / "9606.protein.links.v12.0.txt"
    results.append(_db_check("STRING", string_file, "v12.0"))

    # BioGRID — find any .tab3.txt
    biogrid_files = list(settings.DB_BIOGRID.glob("*.tab3.txt"))
    if biogrid_files:
        f = biogrid_files[0]
        results.append(_db_check("BioGRID", f, f.stem))
    else:
        results.append({"name": "BioGRID", "present": False, "version": None, "size_mb": 0})

    # GTEx
    gtex_files = list(settings.DB_GTEX.glob("*_gene_tpm.*"))
    if gtex_files:
        f = gtex_files[0]
        results.append(_db_check("GTEx", f, "v11"))
    else:
        results.append({"name": "GTEx", "present": False, "version": None, "size_mb": 0})

    # AlphaMissense
    am_file = settings.DB_ALPHAMISSENSE / "AlphaMissense_hg38.tsv"
    results.append(_db_check("AlphaMissense", am_file, "v1"))

    # ChEMBL
    chembl_file = settings.DB_CHEMBL / "chembl_37.db"
    if not chembl_file.exists():
        chembl_files = list(settings.DB_CHEMBL.glob("chembl_*.db"))
        chembl_file = chembl_files[0] if chembl_files else chembl_file
    results.append(_db_check("ChEMBL", chembl_file, "37"))

    # GWAS Catalog
    gwas_assoc = list(settings.DB_GWAS.glob("*associations*.tsv"))
    gwas_studies = list(settings.DB_GWAS.glob("*studies*.tsv"))
    if gwas_assoc:
        results.append(_db_check("GWAS_Catalog_Associations", gwas_assoc[0], "latest"))
    elif gwas_studies:
        results.append({
            "name": "GWAS_Catalog",
            "present": True,
            "version": "studies_only",
            "size_mb": round(gwas_studies[0].stat().st_size / 1_048_576, 1),
            "warning": "Only studies TSV present; download 'All associations' for full Phase 1 support",
        })
    else:
        results.append({"name": "GWAS_Catalog", "present": False, "version": None, "size_mb": 0})

    return results


# ── Credential / endpoint probes ─────────────────────────────────────────────

def _probe(name: str, fn) -> Dict[str, Any]:
    t0 = time.monotonic()
    try:
        detail = fn()
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"service": name, "ok": True, "latency_ms": latency_ms, "detail": detail}
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"service": name, "ok": False, "latency_ms": latency_ms, "detail": str(exc)}


def probe_supabase() -> Dict[str, Any]:
    def _check():
        from src.db.supabase_client import get_service_client
        db = get_service_client()
        db.table("runs").select("id").limit(1).execute()
        return "connected"
    return _probe("Supabase", _check)


def probe_redis() -> Dict[str, Any]:
    def _check():
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=5)
        r.ping()
        return "pong"
    return _probe("Redis", _check)


def probe_lmstudio(base_url: str, model: str) -> Dict[str, Any]:
    def _check():
        resp = httpx.get(f"{base_url.rstrip('/')}/models", timeout=5)
        resp.raise_for_status()
        models = [m["id"] for m in resp.json().get("data", [])]
        if not any(model in m for m in models):
            raise RuntimeError(f"Model '{model}' not found. Available: {models}")
        return f"model '{model}' live"
    return _probe("LMStudio", _check)


def probe_anthropic(api_key: str, model: str) -> Dict[str, Any]:
    def _check():
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=1, messages=[{"role": "user", "content": "hi"}]
        )
        return f"model={resp.model}"
    return _probe("Anthropic", _check)


def probe_openai(api_key: str, model: str) -> Dict[str, Any]:
    def _check():
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        client.models.retrieve(model)
        return f"model={model} live"
    return _probe("OpenAI", _check)


def probe_nim(api_key: str) -> Dict[str, Any]:
    def _check():
        resp = httpx.get(
            "https://api.nvcf.nvidia.com/v2/nvcf/functions",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return "connected"
    return _probe("NVIDIA_NIM", _check)


def probe_ncbi(api_key: str) -> Dict[str, Any]:
    def _check():
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        resp = httpx.get(url, params={"db": "pubmed", "term": "test", "retmax": 1,
                                       "api_key": api_key, "retmode": "json"}, timeout=10)
        resp.raise_for_status()
        count = resp.json()["esearchresult"]["count"]
        return f"reachable, hits={count}"
    return _probe("NCBI_Eutils", _check)


def probe_omim(api_key: str) -> Dict[str, Any]:
    def _check():
        resp = httpx.get(
            "https://api.omim.org/api/entry",
            params={"mimNumber": "100050", "apiKey": api_key, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        return "connected"
    return _probe("OMIM", _check)


def probe_open_targets() -> Dict[str, Any]:
    """Open Targets GraphQL — no auth required."""
    def _check():
        query = '{ meta { dataVersion { year month } } }'
        resp = httpx.post(
            "https://api.platform.opentargets.org/api/v4/graphql",
            json={"query": query},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()["data"]["meta"]["dataVersion"]
        return f"OT {data['year']}-{data['month']}"
    return _probe("OpenTargets", _check)


# ── GPU probe ─────────────────────────────────────────────────────────────────

def probe_gpu() -> Dict[str, Any]:
    try:
        import subprocess
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader,nounits"],
            timeout=10, text=True,
        ).strip().split("\n")
        gpus = []
        for line in out:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2:
                gpus.append({"name": parts[0], "vram_free_mb": int(parts[1])})
        sharing_mode = settings.GPU_SHARING_MODE
        return {"gpus": gpus, "sharing_mode": sharing_mode}
    except Exception as exc:
        return {"gpus": [], "sharing_mode": "none", "error": str(exc)}
