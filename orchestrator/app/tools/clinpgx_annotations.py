"""A real PharmGKB/ClinPGx MCP tool (docs/17-remaining-tools-wiring-
plan.md's "newly identified gaps" section) -- pharmacogenomics: real
gene-drug-variant clinical annotations, a distinct and clinically real
question `dailymed.py` (drug label text) doesn't cover: does this
variant change how a patient metabolizes/responds to this drug.

docs/10-build-plan.md's Phase 3 previously tried and gave up on PharmGKB
-- its old API (api.pharmgkb.org/v1/data/*) no longer resolves, and
every guessed replacement on clinpgx.org (the rebrand) returned the
SPA's HTML shell instead of JSON. Confirmed live (2026-08-26) that the
real successor API is at a different host entirely: api.clinpgx.org --
`GET /v1/data/clinicalAnnotation?location.genes.symbol=<SYMBOL>&view=max`
returns real, structured clinical annotation data (drug, evidence level,
allele-specific phenotype text). This is the actual working endpoint,
not a guess.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

CLINPGX_BASE = "https://api.clinpgx.org/v1/data"


@tool(
    "get_gene_drug_annotations",
    "Given a gene symbol (e.g. 'CYP2D6'), return real PharmGKB/ClinPGx "
    "clinical annotations for that gene: which drugs are affected, the "
    "level of evidence (1A highest to 4 lowest), and the annotation "
    "summary. Answers 'does this variant change how a patient responds "
    "to this drug' -- a distinct question from dailymed.py's label text "
    "(what's approved to claim). Never state an annotation this tool "
    "didn't actually return.",
    {"gene_symbol": str, "max_results": int},
)
async def get_gene_drug_annotations(args: dict[str, Any]) -> dict[str, Any]:
    gene_symbol = (args.get("gene_symbol") or "").strip().upper()
    max_results = min(int(args.get("max_results", 10)), 50)
    if not gene_symbol:
        return {"content": [{"type": "text", "text": "gene_symbol must be non-empty."}]}

    # 30s, not 15s -- a heavily-studied gene (e.g. CYP2D6, 100+
    # annotations) genuinely takes longer under view=max; confirmed live
    # (a real, valid query there hit a 15s ReadTimeout before this was
    # raised, same finding as ensembl_vep.py's BRCA1 case).
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{CLINPGX_BASE}/clinicalAnnotation",
            params={"location.genes.symbol": gene_symbol, "view": "max"},
        )
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PharmGKB/ClinPGx clinical annotations found for gene {gene_symbol!r}."}]}
        resp.raise_for_status()
        data = resp.json()

    records = data.get("data", [])
    if not records:
        return {"content": [{"type": "text", "text": f"No PharmGKB/ClinPGx clinical annotations found for gene {gene_symbol!r}."}]}

    # Sort by evidence level (1A strongest); ties keep API order.
    level_order = {"1A": 0, "1B": 1, "2A": 2, "2B": 3, "3": 4, "4": 5}
    records = sorted(records, key=lambda r: level_order.get((r.get("levelOfEvidence") or {}).get("term", ""), 99))

    lines = [f"PharmGKB/ClinPGx clinical annotations for {gene_symbol} ({len(records)} total, showing {min(len(records), max_results)}):"]
    for rec in records[:max_results]:
        drugs = ", ".join(c["name"] for c in rec.get("relatedChemicals", []))
        level = (rec.get("levelOfEvidence") or {}).get("term", "n/a")
        accession = rec.get("accessionId", "n/a")
        lines.append(f"- [{accession}] {rec.get('name', 'n/a')} -- drug(s): {drugs or 'n/a'}, evidence level {level}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_clinpgx_annotations_mcp_server():
    return create_sdk_mcp_server(name="clinpgx_annotations", tools=[get_gene_drug_annotations])
