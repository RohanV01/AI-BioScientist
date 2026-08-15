"""A real ClinVar MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
built the same way as app/tools/pubmed.py -- NCBI E-utilities, free and
unauthenticated, no separate server process needed.

One tool: search ClinVar for variants in a gene (optionally filtered by
a free-text clinical-significance/condition term) and return each
variant's ClinVar accession, name, clinical significance classification,
review status, and associated condition(s) -- the clinical-genomics
counterpart to Ensembl's gene-identity lookup and Open Targets'
disease-association scores.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@tool(
    "search_variants",
    "Search ClinVar for variants in a gene, optionally narrowed by a "
    "free-text term (e.g. a condition or 'pathogenic'). Returns each "
    "variant's ClinVar accession, name, clinical significance, review "
    "status, and associated condition(s). Use the ClinVar accession as "
    "the citable record reference -- never invent one or state a "
    "classification this tool didn't return.",
    {"gene": str, "term": str, "max_results": int},
)
async def search_variants(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 20)
    query = f"{args['gene']}[gene]"
    extra = (args.get("term") or "").strip()
    if extra:
        query += f" AND {extra}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params={"db": "clinvar", "term": query, "retmode": "json", "retmax": max_results},
        )
        search_resp.raise_for_status()
        uids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not uids:
            return {"content": [{"type": "text", "text": f"No ClinVar variants found for {query!r}."}]}

        summary_resp = await client.get(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(uids), "retmode": "json"},
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

    lines = []
    for uid in uids:
        rec = result.get(uid)
        if not rec:
            continue
        gc = rec.get("germline_classification") or {}
        conditions = ", ".join(
            t.get("trait_name", "") for t in gc.get("trait_set", []) if t.get("trait_name")
        )
        # GRCh38 genomic coordinates, when present -- lets a caller
        # cross-reference this variant against a coordinate-based tool
        # (e.g. gnomAD's get_variant_frequency) without having to parse
        # HGVS/cDNA notation itself. Not every variant type maps cleanly
        # to a single ref/alt pair (indels especially), so this gives
        # chr:start-stop only, not a ready-made gnomAD variant_id.
        coord_bit = ""
        variation_set = rec.get("variation_set") or []
        if variation_set:
            for loc in variation_set[0].get("variation_loc") or []:
                if loc.get("assembly_name") == "GRCh38" and loc.get("status") == "current":
                    coord_bit = f" -- GRCh38 chr{loc['chr']}:{loc['start']}-{loc['stop']}"
                    break
        lines.append(
            f"- ClinVar {rec.get('accession', uid)}: {rec.get('title', '')} -- "
            f"classification: {gc.get('description', 'not classified')} "
            f"({gc.get('review_status', 'unknown review status')}); "
            f"condition(s): {conditions or 'not specified'}{coord_bit}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_clinvar_mcp_server():
    return create_sdk_mcp_server(name="clinvar", tools=[search_variants])
