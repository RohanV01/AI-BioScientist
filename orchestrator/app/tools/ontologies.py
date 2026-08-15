"""A real Ontologies MCP tool (docs/10-build-plan.md Phase 3, Shortlist
#2 -- "the natural point to add it since entity normalization matters
more as the roster grows"), built against EBI's Ontology Lookup Service
(OLS), free and unauthenticated, one API covering every ontology the
research report flagged as missing (Gene Ontology, HPO, MONDO, NCBI
Taxonomy, ICD, and more) rather than wiring each ontology separately.

One tool: search any named ontology (or all of them) for a term and
return its normalized ID, preferred label, and description. The
resolved ID is itself a grounded claim ("seizure normalizes to
HP:0001250") backed by a real tool call, same as any other tool source
-- see claude_runner.py's RECORD_REF_PATTERNS, which matches OLS's
colon-form IDs (MONDO:..., HP:...) alongside the underscore form Open
Targets uses for the same identifiers.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


@tool(
    "search_ontology_term",
    "Search an ontology for a term and return its normalized ID, "
    "preferred label, and description -- for resolving free-text "
    "phenotypes/diseases/processes/organisms/taxa to standard IDs (e.g. "
    "'seizure' -> HP:0001250). Pass ontology to restrict the search: "
    "'go' (Gene Ontology, biological processes/functions/components), "
    "'hp' (Human Phenotype Ontology), 'mondo' (disease), 'ncbitaxon' "
    "(organism/taxon), 'icd10'/'icd9' (clinical coding). Omit ontology "
    "to search across all of them.",
    {"query": str, "ontology": str, "max_results": int},
)
async def search_ontology_term(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    params: dict[str, Any] = {"q": args["query"], "rows": max_results}
    ontology = (args.get("ontology") or "").strip()
    if ontology:
        params["ontology"] = ontology

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(OLS_SEARCH_URL, params=params)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])

    if not docs:
        return {"content": [{"type": "text", "text": f"No ontology terms found for {args['query']!r}."}]}

    lines = []
    for d in docs:
        obo_id = d.get("obo_id", d.get("short_form", "unknown"))
        label = d.get("label", "")
        prefix = d.get("ontology_prefix", "")
        description = (d.get("description") or [""])[0]
        desc_bit = f" -- {description[:200]}" if description else ""
        lines.append(f"- {obo_id} ({prefix}): {label}{desc_bit}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_ontologies_mcp_server():
    return create_sdk_mcp_server(name="ontologies", tools=[search_ontology_term])
