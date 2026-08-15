"""A real ChEMBL MCP tool, built the same way as app/tools/pubmed.py:
in-process via the Claude Agent SDK's @tool/create_sdk_mcp_server, hitting
ChEMBL's free/public REST API directly -- no separate server process, no
auth needed.

Two tools, matching names already used throughout docs/ and the research
report: compound_search (find a compound, get its ChEMBL ID + key
properties) and get_bioactivity (known activities against targets for a
compound). Deliberately not porting every function the report's live
ChEMBL MCP connector had (target_search, get_mechanism, drug_search,
get_admet) -- these two cover the highest-value path (find a compound,
see what it's active against) and more can be added the same way once
there's a real task that needs them (docs/10-build-plan.md Phase 3 is
demand-driven roster growth, not upfront completeness).
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"


@tool(
    "compound_search",
    "Search ChEMBL for a compound by name (e.g. a drug name). Returns "
    "ChEMBL ID, molecular formula, max clinical phase, and key properties "
    "for each match -- use the ChEMBL ID as the citable record reference, "
    "never invent one.",
    {"query": str, "max_results": int},
)
async def compound_search(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    max_results = min(int(args.get("max_results", 5)), 20)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{CHEMBL_BASE}/molecule/search",
            params={"q": query, "format": "json", "limit": max_results},
        )
        resp.raise_for_status()
        molecules = resp.json().get("molecules", [])

    if not molecules:
        return {"content": [{"type": "text", "text": f"No ChEMBL compounds found for {query!r}."}]}

    lines = []
    for m in molecules:
        props = m.get("molecule_properties") or {}
        lines.append(
            f"- ChEMBL ID {m['molecule_chembl_id']}: "
            f"{(m.get('pref_name') or 'no preferred name')}, "
            f"formula {props.get('full_molformula', 'n/a')}, "
            f"MW {props.get('full_mwt', 'n/a')}, "
            f"max clinical phase {m.get('max_phase', 'n/a')}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_bioactivity",
    "Given a ChEMBL compound ID, return its known bioactivity records "
    "(target, assay type, potency value) from ChEMBL. Use the ChEMBL "
    "compound/target IDs and reported values as citable facts -- never "
    "state a potency value this tool didn't return.",
    {"chembl_id": str, "max_results": int},
)
async def get_bioactivity(args: dict[str, Any]) -> dict[str, Any]:
    chembl_id = args["chembl_id"]
    max_results = min(int(args.get("max_results", 10)), 30)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{CHEMBL_BASE}/activity",
            params={
                "molecule_chembl_id": chembl_id,
                "format": "json",
                "limit": max_results,
                "standard_type__in": "IC50,EC50,Ki,Kd",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        activities = data.get("activities", [])
        total = data.get("page_meta", {}).get("total_count", len(activities))

    if not activities:
        return {"content": [{"type": "text", "text": f"No bioactivity records found for ChEMBL ID {chembl_id}."}]}

    lines = [f"Bioactivity for ChEMBL ID {chembl_id} ({total} total records, showing {len(activities)}):"]
    for a in activities:
        lines.append(
            f"- Target {a.get('target_chembl_id', 'n/a')} ({a.get('target_organism', 'n/a')}): "
            f"{a.get('standard_type', 'n/a')} = {a.get('standard_value', 'n/a')} {a.get('standard_units', '')} "
            f"(pChEMBL {a.get('pchembl_value', 'n/a')}) -- {a.get('assay_description', 'no description')}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_chembl_mcp_server():
    return create_sdk_mcp_server(name="chembl", tools=[compound_search, get_bioactivity])
