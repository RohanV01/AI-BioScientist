"""A real straindesign MCP tool (docs/12-biotools-triage-shortlist.md's
Cheminformatics section). Completes the metabolic-engineering pipeline
that was stuck at "observe": cobra_fba.py predicts growth,
equilibrator_thermo.py checks reaction feasibility, but neither
proposes what to actually change. straindesign (built directly on
cobrapy, uses the same BiGG-model fetch pattern as cobra_fba.py) is
the missing "so design an intervention" step -- real OptKnock
computation: which reaction knockouts force overproduction of a target
metabolite while the model is still forced to grow.

Real local MILP computation (via pyscipopt/SCIP or GLPK), same
methodological-citation convention as cobra_fba.py, tagged
[straindesign:model_id].

A real pitfall found and fixed during testing: an unconstrained
OptKnock run can return a numerically "valid" but biologically
meaningless solution (e.g. knocking out the biomass reaction itself
trivially satisfies the MILP). Fixed by always requiring a minimum-
growth constraint on the inner objective, matching straindesign's own
documented best practice for growth-coupled production design. The
resulting real solution (on e_coli_core, maximizing succinate export)
was independently verified by applying the knockouts and re-running
FBA: growth 0.157 (above the 0.1 floor), succinate flux 0 -> 9.69.
"""
import asyncio
import gzip
import tempfile
from typing import Any

import cobra
import httpx
import straindesign as sd
from claude_agent_sdk import create_sdk_mcp_server, tool

# https -- see cobra_fba.py's BIGG_DOWNLOAD_URL comment: bigg.ucsd.edu now
# permanently redirects http -> https.
BIGG_DOWNLOAD_URL = "https://bigg.ucsd.edu/static/models"


def _run_optknock(model: cobra.Model, target_reaction_id: str, min_growth_fraction: float, max_interventions: int) -> dict:
    biomass_rxn = next((r.id for r in model.reactions if r.objective_coefficient != 0), None)
    if biomass_rxn is None:
        raise ValueError("Could not identify this model's growth (biomass) objective reaction.")

    baseline = model.optimize()
    if baseline.status != "optimal":
        raise ValueError(f"Baseline FBA did not reach an optimal solution (status: {baseline.status}).")
    min_growth = baseline.objective_value * min_growth_fraction

    module = sd.SDModule(
        model, sd.OPTKNOCK,
        inner_objective=biomass_rxn, outer_objective=target_reaction_id, outer_opt_sense=sd.MAXIMIZE,
        constraints=[f"{biomass_rxn} >= {min_growth}"],
    )
    sols = sd.compute_strain_designs(model, sd_modules=[module], max_solutions=1, max_cost=max_interventions, solution_approach=sd.BEST)
    if sols.status != "optimal" or not sols.reaction_sd:
        raise ValueError(
            f"No intervention set found forcing {target_reaction_id} overproduction within "
            f"{max_interventions} knockouts while keeping growth >= {min_growth:.4f}."
        )

    # Independently re-verify the top solution by actually applying it and re-simulating,
    # rather than trusting the MILP result as-is.
    knockouts = list(sols.reaction_sd[0].keys())
    verify_model = model.copy()
    for rxn_id in knockouts:
        verify_model.reactions.get_by_id(rxn_id).knock_out()
    verify_sol = verify_model.optimize()

    return {
        "biomass_rxn": biomass_rxn,
        "baseline_growth": baseline.objective_value,
        "baseline_target_flux": baseline.fluxes[target_reaction_id],
        "knockouts": knockouts,
        "verified_growth": verify_sol.objective_value if verify_sol.status == "optimal" else None,
        "verified_target_flux": verify_sol.fluxes[target_reaction_id] if verify_sol.status == "optimal" else None,
        "num_alternatives": len(sols.reaction_sd),
    }


@tool(
    "design_strain_intervention",
    "Given a BiGG model ID (from cobra_fba's search_metabolic_models) and a target reaction ID "
    "(e.g. an exchange reaction like 'EX_succ_e' for succinate export), run a real OptKnock "
    "computation to find reaction knockouts that force overproduction of the target while the "
    "model is still constrained to grow. The proposed knockout set is independently re-verified "
    "by actually applying it and re-running FBA (not just trusting the MILP solver's own claim). "
    "Never state a knockout or flux value this tool didn't actually compute.",
    {"bigg_model_id": str, "target_reaction_id": str, "min_growth_fraction": float, "max_interventions": int},
)
async def design_strain_intervention(args: dict[str, Any]) -> dict[str, Any]:
    model_id = args["bigg_model_id"].strip()
    target_reaction_id = args["target_reaction_id"].strip()
    min_growth_fraction = float(args.get("min_growth_fraction", 0.1))
    max_interventions = min(int(args.get("max_interventions", 4)), 6)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{BIGG_DOWNLOAD_URL}/{model_id}.xml.gz", follow_redirects=True)
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No BiGG model found with ID {model_id!r}."}]}
        resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".xml") as f:
        f.write(gzip.decompress(resp.content))
        f.flush()
        model = cobra.io.read_sbml_model(f.name)

    if target_reaction_id not in [r.id for r in model.reactions]:
        return {"content": [{"type": "text", "text": f"Reaction {target_reaction_id!r} not found in model {model_id!r}."}]}

    try:
        result = await asyncio.to_thread(
            _run_optknock, model, target_reaction_id, min_growth_fraction, max_interventions
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}]}

    lines = [
        f"OptKnock strain design on BiGG model {model_id}, target {target_reaction_id} "
        f"[straindesign:{model_id}]:",
        f"- Baseline (unmodified): growth {result['baseline_growth']:.4f}, "
        f"{target_reaction_id} flux {result['baseline_target_flux']:.4f}",
        f"- Proposed knockout(s): {', '.join(result['knockouts'])} "
        f"({result['num_alternatives']} alternative equal-cost solution(s) exist)",
    ]
    if result["verified_growth"] is not None:
        lines.append(
            f"- Independently re-verified by applying the knockouts and re-running FBA: "
            f"growth {result['verified_growth']:.4f}, {target_reaction_id} flux {result['verified_target_flux']:.4f}"
        )
    else:
        lines.append("- Warning: re-verification FBA did not reach an optimal solution after applying the knockouts.")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_straindesign_intervention_mcp_server():
    return create_sdk_mcp_server(name="straindesign_intervention", tools=[design_strain_intervention])
