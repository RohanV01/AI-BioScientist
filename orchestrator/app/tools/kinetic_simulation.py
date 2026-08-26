"""A real libRoadRunner MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 1, Cheminformatics cluster) -- dynamic (time-course) SBML kinetic
simulation, complementing the already-live `cobra_fba` tool's
steady-state flux balance analysis. FBA answers "what's the long-run
optimal flux distribution"; this answers "how does concentration X change
over time" -- a genuinely different question neither tool can answer for
the other.

docs/17 lists libRoadRunner and basico as the same niche via alternate
APIs ("Same SBML kinetic simulation niche, alternate API") -- built only
libRoadRunner here (the more established, C++-backed engine) rather than
both, same precedent as this codebase already set for KEGG/Reactome/
STRING each covering a genuinely distinct capability rather than wiring
every API with overlapping scope.

Fetches real curated kinetic models from BioModels (free, unauthenticated
REST API) by their real BioModels ID -- the citable record reference --
rather than accepting arbitrary caller-supplied SBML, keeping this
consistent with every other external-API tool in the roster (a real
database record backs the result, not just a computation on opaque
caller input).
"""
from typing import Any

import httpx
import roadrunner
from claude_agent_sdk import create_sdk_mcp_server, tool

BIOMODELS_DOWNLOAD_URL = "https://www.ebi.ac.uk/biomodels/model/download/{model_id}"


@tool(
    "simulate_kinetic_model",
    "Given a BioModels ID (e.g. 'BIOMD0000000012'), fetch the real curated "
    "SBML kinetic model and run a real time-course ODE simulation via "
    "libRoadRunner. Returns each tracked species' initial and final "
    "concentration/amount over the requested duration -- use for dynamic "
    "questions (how does X change over time) that steady-state FBA "
    "(cobra_fba) cannot answer. Use the BioModels ID as the citable "
    "record reference. Never state a concentration this tool didn't "
    "actually compute.",
    {"biomodels_id": str, "duration": float, "steps": int},
)
async def simulate_kinetic_model(args: dict[str, Any]) -> dict[str, Any]:
    model_id = (args.get("biomodels_id") or "").strip()
    duration = float(args.get("duration", 100))
    steps = min(int(args.get("steps", 20)), 200)

    if not model_id:
        return {"content": [{"type": "text", "text": "biomodels_id must be non-empty, e.g. 'BIOMD0000000012'."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(
            BIOMODELS_DOWNLOAD_URL.format(model_id=model_id),
            params={"filename": f"{model_id}_url.xml"},
        )
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No BioModels entry found for ID {model_id!r}."}]}
        resp.raise_for_status()
        sbml = resp.text

    try:
        rr = roadrunner.RoadRunner(sbml)
        result = rr.simulate(0, duration, steps)
    except Exception as exc:  # noqa: BLE001 -- surface real libRoadRunner/SBML errors to the caller
        return {"content": [{"type": "text", "text": f"Simulation failed for BioModels {model_id}: {exc}"}]}

    colnames = result.colnames  # ['time', '[SpeciesA]', '[SpeciesB]', ...]
    species_cols = [c for c in colnames if c != "time"]
    first_row, last_row = result[0], result[-1]

    # [libroadrunner:sim] is the citable methodological tag for the
    # simulation itself; BioModels ID <model_id> is the citable record
    # reference for the model that was simulated.
    lines = [
        f"BioModels {model_id} -- time-course simulation over {duration} time units "
        f"({steps} steps) via libRoadRunner [libroadrunner:sim]:"
    ]
    for col in species_cols:
        idx = colnames.index(col)
        lines.append(f"- {col.strip('[]')}: initial {first_row[idx]:.6g} -> final {last_row[idx]:.6g}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_kinetic_simulation_mcp_server():
    return create_sdk_mcp_server(name="kinetic_simulation", tools=[simulate_kinetic_model])
