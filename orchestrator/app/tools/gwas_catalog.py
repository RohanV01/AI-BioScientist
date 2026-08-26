"""A real pandasGWAS MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Population genetics cluster) -- programmatic access to the
NHGRI-EBI GWAS Catalog, a real published-study index distinct from what
`ensembl_vep`/`gnomad` (variant-level population/functional data) or
`open_targets` (target-disease association scores) already cover: given
a variant, which specific published GWAS studies found a trait
association for it, with the study's real accession ID and source
publication.

Confirmed live before wiring (2026-08-26): `get_studies_by_variant_id`
on a real, well-studied variant (rs7412, the APOE epsilon2 SNP) took
~60-90s to return -- genuinely slow (the GWAS Catalog API paginating a
large real result set, not a hang; a second run against a different
variant showed the same latency pattern) but not unreliable. Set a
generous 180s timeout accordingly, and documented the latency plainly in
this tool's own description so the calling agent doesn't mistake a long
wait for a stall.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_TIMEOUT_SECONDS = 180


@tool(
    "get_gwas_studies_for_variant",
    "Given a real dbSNP variant ID (e.g. 'rs7412'), query the NHGRI-EBI "
    "GWAS Catalog for published genome-wide association studies that "
    "found a trait association for it -- real study accession IDs "
    "(GCST...), the associated trait, and the source publication (PMID). "
    "Distinct from ensembl_vep (functional consequence prediction) and "
    "open_targets (target-disease scores): this is the actual published "
    "GWAS evidence trail. This call is genuinely slow (the GWAS Catalog "
    "API can take 60-180s to paginate a full result set for a "
    "well-studied variant) -- that is expected, not a stall. Never state "
    "a study/trait/PMID this tool didn't actually return.",
    {"variant_id": str, "max_results": int},
)
async def get_gwas_studies_for_variant(args: dict[str, Any]) -> dict[str, Any]:
    variant_id = (args.get("variant_id") or "").strip().lower()
    max_results = min(int(args.get("max_results", 10)), 30)
    if not variant_id.startswith("rs") or not variant_id[2:].isdigit():
        return {"content": [{"type": "text", "text": "variant_id must be a real dbSNP rsID, e.g. 'rs7412'."}]}

    import asyncio

    def _run():
        import pandasgwas

        return pandasgwas.get_studies_by_variant_id(variant_id)

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_run), timeout=MAX_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return {"content": [{"type": "text", "text": f"GWAS Catalog query for {variant_id} timed out after {MAX_TIMEOUT_SECONDS}s."}]}
    except Exception as exc:  # noqa: BLE001 -- surface real pandasgwas/API errors to the caller
        return {"content": [{"type": "text", "text": f"GWAS Catalog query failed: {exc}"}]}

    studies = result.studies
    if studies is None or studies.empty:
        return {"content": [{"type": "text", "text": f"No GWAS Catalog studies found for {variant_id}."}]}

    lines = [f"GWAS Catalog studies for {variant_id} [pandasGWAS:{variant_id}] -- top {min(len(studies), max_results)} of {len(studies)}:"]
    for _, row in studies.head(max_results).iterrows():
        trait = row.get("diseaseTrait.trait", "unknown trait")
        pmid = row.get("publicationInfo.pubmedId", "unknown")
        sample = row.get("initialSampleSize", "unknown sample size")
        lines.append(f"- study {row.get('accessionId', 'unknown')}: {trait} (PMID {pmid}, sample: {sample})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_gwas_catalog_mcp_server():
    return create_sdk_mcp_server(name="gwas_catalog", tools=[get_gwas_studies_for_variant])
