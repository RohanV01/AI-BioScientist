"""A real Human Phenotype Ontology (HPO) MCP tool (docs/17-remaining-
tools-wiring-plan.md's "newly identified gaps" section) -- structured
phenotype-to-disease associations via HPO's own free, unauthenticated
REST API (ontology.jax.org). `ontologies.py`'s generic OLS-backed search
covers term lookup/definitions across many ontologies but not HPO's
specific disease-association graph.

Confirmed the real API contract live before wiring (2026-08-26):
- GET /api/hp/search?q=<text>&max=<n> -- free-text term search.
- GET /api/network/annotation/<HP_ID> -- diseases associated with a term.
(A `/genes` variant was tried and does not exist on this API -- not
guessed, confirmed absent before settling on the disease-association
shape that does work.)
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

HPO_BASE = "https://ontology.jax.org/api"


@tool(
    "get_phenotype_diseases",
    "Given a specific clinical phenotype (either an HPO term ID like "
    "'HP:0001250', or free text like 'seizure' which is resolved to its "
    "best-matching HPO term first), return the diseases associated with "
    "that phenotype in HPO's own curated annotation graph. Returns each "
    "disease's ID (OMIM/ORPHA), name, and MONDO cross-reference where "
    "available. Never state a disease association this tool didn't "
    "actually return.",
    {"phenotype": str, "max_results": int},
)
async def get_phenotype_diseases(args: dict[str, Any]) -> dict[str, Any]:
    phenotype = (args.get("phenotype") or "").strip()
    max_results = min(int(args.get("max_results", 15)), 50)
    if not phenotype:
        return {"content": [{"type": "text", "text": "phenotype must be non-empty."}]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        hp_id = phenotype
        if not phenotype.upper().startswith("HP:"):
            search_resp = await client.get(f"{HPO_BASE}/hp/search", params={"q": phenotype, "max": 1})
            search_resp.raise_for_status()
            terms = search_resp.json().get("terms", [])
            if not terms:
                return {"content": [{"type": "text", "text": f"No HPO term found matching {phenotype!r}."}]}
            hp_id = terms[0]["id"]
            resolved_name = terms[0]["name"]
        else:
            resolved_name = None

        assoc_resp = await client.get(f"{HPO_BASE}/network/annotation/{hp_id}")
        if assoc_resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No HPO term found for {hp_id!r}."}]}
        assoc_resp.raise_for_status()
        diseases = assoc_resp.json().get("diseases", [])

    if not diseases:
        return {"content": [{"type": "text", "text": f"No disease associations found for HPO term {hp_id}."}]}

    header = f"Diseases associated with HPO term {hp_id}"
    if resolved_name:
        header += f" ({resolved_name!r}, resolved from {phenotype!r})"
    lines = [f"{header} -- {len(diseases)} total, showing {min(len(diseases), max_results)}:"]
    for d in diseases[:max_results]:
        mondo = f", {d['mondoId']}" if d.get("mondoId") else ""
        lines.append(f"- {d['id']}: {d['name']}{mondo}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_hpo_mcp_server():
    return create_sdk_mcp_server(name="hpo", tools=[get_phenotype_diseases])
