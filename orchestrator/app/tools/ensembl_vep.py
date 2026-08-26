"""A real Ensembl VEP (Variant Effect Predictor) MCP tool (docs/17-
remaining-tools-wiring-plan.md's "newly identified gaps" section) --
Ensembl's own free, unauthenticated REST API, same host as the already-
live `ensembl.py`. Predicts the functional consequence of a variant that
isn't already curated in ClinVar -- a real gap `clinvar.py`/`gnomad.py`
can't fill, since both only answer "what's already known about this
variant", not "what would this genomic change actually do."

Confirmed the real API contract live before wiring (2026-08-26):
GET /vep/human/hgvs/<hgvs_genomic_notation>?content-type=application/json,
e.g. "17:g.43094692G>A".
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

VEP_BASE = "https://rest.ensembl.org/vep/human/hgvs"


@tool(
    "predict_variant_effect",
    "Given a variant in HGVS genomic notation (e.g. '17:g.43094692G>A' -- "
    "chromosome:g.position<ref>><alt>), predict its functional consequence "
    "via Ensembl VEP: the most severe consequence type (e.g. "
    "missense_variant, stop_gained, synonymous_variant), and per-gene "
    "impact (HIGH/MODERATE/LOW/MODIFIER) for each overlapping transcript's "
    "gene. Answers 'what would this variant do' for a variant not yet "
    "curated in ClinVar -- complements clinvar.py/gnomad.py, which only "
    "answer what's already known/how common a variant is. Never state a "
    "consequence this tool didn't actually return.",
    {"hgvs_notation": str},
)
async def predict_variant_effect(args: dict[str, Any]) -> dict[str, Any]:
    hgvs = (args.get("hgvs_notation") or "").strip()
    if not hgvs:
        return {"content": [{"type": "text", "text": "hgvs_notation must be non-empty, e.g. '17:g.43094692G>A'."}]}

    # 30s, not 15s -- a gene-dense region (e.g. BRCA1) can return 50+
    # transcript consequences and genuinely takes longer than a simple
    # lookup; confirmed live (a real, valid query there hit a 15s
    # ReadTimeout before this was raised).
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{VEP_BASE}/{hgvs}", params={"content-type": "application/json"})
        # Ensembl VEP returns 500 (not 400) for unparseable HGVS input,
        # with a distinguishing {"error": "Unable to parse HGVS..."}
        # body -- confirmed live, not assumed from REST convention. Only
        # treat a 500 as a parse error when that specific message is
        # present, so a genuine server error on valid input still
        # surfaces via raise_for_status() below instead of being
        # silently mislabeled.
        if resp.status_code in (400, 500):
            try:
                err_msg = resp.json().get("error", "")
            except ValueError:
                err_msg = ""
            if "unable to parse hgvs" in err_msg.lower() or resp.status_code == 400:
                return {"content": [{"type": "text", "text": f"Ensembl VEP could not parse {hgvs!r} -- check it's valid HGVS genomic notation."}]}
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return {"content": [{"type": "text", "text": f"No VEP prediction returned for {hgvs!r}."}]}

    result = results[0]
    most_severe = result.get("most_severe_consequence", "unknown")
    tcs = result.get("transcript_consequences", [])

    # Dedup by gene symbol, keep the highest-impact consequence per gene.
    impact_rank = {"HIGH": 3, "MODERATE": 2, "LOW": 1, "MODIFIER": 0}
    by_gene: dict[str, dict] = {}
    for tc in tcs:
        symbol = tc.get("gene_symbol") or tc.get("gene_id", "unknown")
        existing = by_gene.get(symbol)
        if existing is None or impact_rank.get(tc.get("impact", ""), -1) > impact_rank.get(existing.get("impact", ""), -1):
            by_gene[symbol] = tc

    lines = [f"Ensembl VEP prediction for {hgvs}: most severe consequence = {most_severe}"]
    for symbol, tc in sorted(by_gene.items(), key=lambda kv: -impact_rank.get(kv[1].get("impact", ""), -1)):
        terms = ", ".join(tc.get("consequence_terms", []))
        gene_id = tc.get("gene_id", "n/a")
        # Include the real Ensembl Gene ID (ENSG...), not just the
        # symbol -- claude_runner.py's existing "Ensembl Gene ID {}"
        # pattern needs it present in the text to make this citable.
        lines.append(f"- gene {symbol} ({gene_id}): {terms} (impact {tc.get('impact', 'n/a')})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_ensembl_vep_mcp_server():
    return create_sdk_mcp_server(name="ensembl_vep", tools=[predict_variant_effect])
