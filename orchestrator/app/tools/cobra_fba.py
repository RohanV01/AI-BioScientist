"""A real cobrapy MCP tool (docs/10-build-plan.md Phase 5's bio.tools +
GitHub-repo triage -- cobrapy, 579+ GitHub stars, general-purpose,
actively maintained, resolved cleanly via `uv pip install --dry-run`
alongside the already-wired scikit-bio/BioPandas). Runs in-process,
same pattern as scikit_bio.py/biopandas_structure.py.

Genome-scale metabolic models come from BiGG Models
(bigg.ucsd.edu -- 108 published, curated models), a real, standard
public data source, not something invented for this tool. This is a
genuinely distinct capability from KEGG/Reactome (both are static
pathway *lookup*): flux balance analysis actually *simulates* a
metabolic network to predict growth rate and reaction flux
distribution under a given nutrient environment.

Two tools: search BiGG for a model by organism name, then run flux
balance analysis on a chosen model ID.
"""
import gzip
import tempfile
from typing import Any

import cobra
import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

# http:// -- BiGG's own site now permanently redirects to https, confirmed
# live via a real 301 hit; using https directly avoids the extra redirect
# hop (and BIGG_SEARCH_URL's own client.get() call below never passed
# follow_redirects, so it hard-failed on the 301 outright).
BIGG_SEARCH_URL = "https://bigg.ucsd.edu/api/v2/search"
BIGG_DOWNLOAD_URL = "https://bigg.ucsd.edu/static/models"


@tool(
    "search_metabolic_models",
    "Search BiGG Models (bigg.ucsd.edu, 108 published genome-scale "
    "metabolic reconstructions) for models matching an organism name. "
    "Returns each model's BiGG ID and reaction/metabolite/gene counts. "
    "Use the BiGG ID with run_flux_balance_analysis. Never invent a "
    "BiGG ID this tool didn't return.",
    {"organism_query": str, "max_results": int},
)
async def search_metabolic_models(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 20)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(BIGG_SEARCH_URL, params={"query": args["organism_query"], "search_type": "models"})
        resp.raise_for_status()
        results = resp.json().get("results", [])[:max_results]

    if not results:
        return {"content": [{"type": "text", "text": f"No BiGG models found for {args['organism_query']!r}."}]}

    lines = [
        f"- BiGG model {m['bigg_id']}: {m['organism']} "
        f"({m['reaction_count']} reactions, {m['metabolite_count']} metabolites, {m['gene_count']} genes)"
        for m in results
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "run_flux_balance_analysis",
    "Given a BiGG model ID (from search_metabolic_models), download the "
    "real published metabolic reconstruction and run flux balance "
    "analysis (FBA) -- predicts the model's optimal growth rate and its "
    "top-flux reactions under default conditions. Never state a growth "
    "rate or flux value this tool didn't actually compute.",
    {"bigg_model_id": str, "top_n_fluxes": int},
)
async def run_flux_balance_analysis(args: dict[str, Any]) -> dict[str, Any]:
    model_id = args["bigg_model_id"].strip()
    top_n = min(int(args.get("top_n_fluxes", 5)), 20)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{BIGG_DOWNLOAD_URL}/{model_id}.xml.gz", follow_redirects=True)
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No BiGG model found with ID {model_id!r}."}]}
        resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        f.write(gzip.decompress(resp.content))
        f.flush()
        model = cobra.io.read_sbml_model(f.name)

    solution = model.optimize()
    if solution.status != "optimal":
        return {
            "content": [
                {"type": "text", "text": f"BiGG model {model_id} FBA did not reach an optimal solution (status: {solution.status})."}
            ]
        }

    top_fluxes = solution.fluxes.abs().sort_values(ascending=False).head(top_n)
    lines = [
        f"BiGG model {model_id} ({len(model.reactions)} reactions, {len(model.metabolites)} metabolites, {len(model.genes)} genes):",
        f"- Predicted optimal growth rate [cobra:{model_id}]: {solution.objective_value:.4f} (objective: {model.objective.expression})",
        f"Top {top_n} reactions by absolute flux:",
    ]
    for rxn_id, flux in top_fluxes.items():
        rxn = model.reactions.get_by_id(rxn_id)
        lines.append(f"- {rxn_id} ({rxn.name}): flux {solution.fluxes[rxn_id]:.4f}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_cobra_fba_mcp_server():
    return create_sdk_mcp_server(name="cobra_fba", tools=[search_metabolic_models, run_flux_balance_analysis])
