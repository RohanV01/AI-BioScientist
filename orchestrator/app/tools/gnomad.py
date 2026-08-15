"""A real gnomAD MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
same in-process pattern as the other tools -- gnomAD's GraphQL API is
free and unauthenticated.

One tool: given a specific variant (chrom-pos-ref-alt, GRCh38), return
its population allele frequency overall and per continental population
-- the population-genetics counterpart to ClinVar's clinical
classification. The natural pairing this unlocks: a ClinVar hit's
rarity in the general population is direct supporting/contradicting
evidence for a pathogenicity call.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"

# Continental population codes only -- gnomAD's raw population list also
# includes each of these split by chromosomal sex (afr_XX, afr_XY, ...)
# plus overall XX/XY, which would double the output for no analytical
# value here.
CONTINENTAL_POPULATIONS = {"afr", "amr", "asj", "eas", "fin", "mid", "nfe", "remaining", "sas"}

VARIANT_QUERY = """
query($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variant_id
    rsids
    exome { ac an af populations { id ac an } }
    genome { ac an af populations { id ac an } }
  }
}
"""


def _format_cohort(label: str, cohort: dict | None) -> list[str]:
    if cohort is None:
        return [f"{label}: not covered in this dataset"]
    lines = [f"{label}: allele frequency {cohort['af']:.6g} ({cohort['ac']}/{cohort['an']} alleles)"]
    for pop in cohort.get("populations", []):
        if pop["id"] in CONTINENTAL_POPULATIONS and pop["an"] > 0:
            af = pop["ac"] / pop["an"]
            lines.append(f"    - {pop['id']}: {af:.6g} ({pop['ac']}/{pop['an']})")
    return lines


@tool(
    "get_variant_frequency",
    "Look up a specific genomic variant's population allele frequency in "
    "gnomAD. variant_id must be chrom-pos-ref-alt on GRCh38 (e.g. "
    "'17-43045607-A-T') -- not an rsID or HGVS notation. Returns overall "
    "and per-continental-population frequency from exome and genome "
    "cohorts. Never state a frequency this tool didn't return.",
    {"variant_id": str},
)
async def get_variant_frequency(args: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GNOMAD_URL,
            json={
                "query": VARIANT_QUERY,
                "variables": {"variantId": args["variant_id"], "dataset": "gnomad_r4"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        errors = data.get("errors") or []
        if errors and any("not found" in e.get("message", "").lower() for e in errors):
            return {
                "content": [
                    {"type": "text", "text": f"No gnomAD record found for variant {args['variant_id']!r} (GRCh38, gnomad_r4)."}
                ]
            }
        if errors:
            raise RuntimeError(f"gnomAD GraphQL error: {errors}")
        variant = data["data"]["variant"]

    if variant is None:
        return {
            "content": [
                {"type": "text", "text": f"No gnomAD record found for variant {args['variant_id']!r} (GRCh38, gnomad_r4)."}
            ]
        }

    rsids = ", ".join(variant.get("rsids") or []) or "none"
    lines = [f"gnomAD variant {variant['variant_id']} (rsIDs: {rsids}):"]
    lines += _format_cohort("Exome", variant.get("exome"))
    lines += _format_cohort("Genome", variant.get("genome"))
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_gnomad_mcp_server():
    return create_sdk_mcp_server(name="gnomad", tools=[get_variant_frequency])
