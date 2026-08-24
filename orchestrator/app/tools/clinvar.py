"""A real ClinVar MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
built the same way as app/tools/pubmed.py -- NCBI E-utilities, free and
unauthenticated, no separate server process needed.

One tool, two ways to search: by gene (optionally filtered by a free-text
clinical-significance/condition term), or by exact GRCh38 genomic
coordinate (chrom-pos-ref-alt, the same variant_id shape
app/tools/gnomad.py already uses) -- a real gap found by battle-testing
the platform with hard questions: a researcher handed a bare
chrom-pos-ref-alt variant (the natural output of a gnomAD lookup, or of
any VCF-based workflow) previously had no way to look that exact variant
up in ClinVar without already knowing its gene symbol. Returns each
variant's ClinVar accession, name, clinical significance classification,
review status, and associated condition(s). Use the ClinVar accession as
the citable record reference -- never invent one or state a
classification this tool didn't return.
"""
import re
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# "17-43104913-A-T" -- same chrom-pos-ref-alt shape gnomad.py's
# get_variant_frequency documents wanting, so a variant found there can be
# handed straight to this tool without reformatting.
_VARIANT_ID_RE = re.compile(r"^([0-9XYM]{1,2})-(\d+)-[ACGT]+-[ACGT]+$", re.IGNORECASE)


@tool(
    "search_variants",
    "Search ClinVar for variants, either by gene (optionally narrowed by a "
    "free-text term, e.g. a condition or 'pathogenic') or by an exact "
    "GRCh38 genomic coordinate via variant_id in chrom-pos-ref-alt format "
    "(e.g. '17-43104913-A-T', the same format gnomAD's get_variant_frequency "
    "uses) -- provide one or the other, not both. Returns each variant's "
    "ClinVar accession, name, clinical significance, review status, and "
    "associated condition(s). Use the ClinVar accession as the citable "
    "record reference -- never invent one or state a classification this "
    "tool didn't return.",
    {"gene": str, "term": str, "variant_id": str, "max_results": int},
)
async def search_variants(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 20)
    variant_id = (args.get("variant_id") or "").strip()
    gene = (args.get("gene") or "").strip()

    if variant_id:
        match = _VARIANT_ID_RE.match(variant_id)
        if not match:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"variant_id {variant_id!r} must be chrom-pos-ref-alt format "
                            "(e.g. '17-43104913-A-T'), not an rsID or HGVS notation."
                        ),
                    }
                ]
            }
        chrom, pos = match.group(1), match.group(2)
        # Position alone isn't unique across the genome (a bare
        # 43045607[chrpos38] hit a real record on chr6, not the intended
        # chr17 one, confirmed live) -- chromosome + position together is
        # the minimum for a real answer.
        query = f"{chrom}[chromosome] AND {pos}[chrpos38]"
    elif gene:
        query = f"{gene}[gene]"
        extra = (args.get("term") or "").strip()
        if extra:
            query += f" AND {extra}"
    else:
        return {"content": [{"type": "text", "text": "Provide either gene or variant_id."}]}

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
