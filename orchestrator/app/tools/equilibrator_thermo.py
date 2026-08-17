"""A real eQuilibrator MCP tool (docs/12-biotools-triage-shortlist.md's
Cheminformatics cluster). Reports the standard Gibbs free energy change
of a biochemical reaction -- the thermodynamic complement to
app/tools/cobra_fba.py's flux balance analysis: FBA tells you a
reaction *can* carry flux at steady state, eQuilibrator tells you
whether it's thermodynamically favorable in the first place (dG < 0)
or requires being pulled/pushed by coupled reactions (dG > 0).

Uses the Component Contribution method (a group-contribution +
machine-learning hybrid) via the real equilibrator-api package,
in-process. Reactions are given in KEGG-ID formula notation (e.g.
"kegg:C00002 + kegg:C00001 = kegg:C00008 + kegg:C00009" for ATP
hydrolysis) since that's eQuilibrator's own native reaction format and
pairs naturally with the existing kegg.py tool's compound/pathway IDs.
Real local computation against a bundled reference dataset, no
external API call for the calculation itself -- citable tag
[equilibrator:reaction].
"""
import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

_cc = None


def _get_cc():
    global _cc
    if _cc is None:
        from equilibrator_api import ComponentContribution

        _cc = ComponentContribution()
    return _cc


def _run_dg_prime(reaction_formula: str) -> str:
    cc = _get_cc()
    reaction = cc.parse_reaction_formula(reaction_formula)
    if not reaction.is_balanced():
        raise ValueError(f"Reaction is not balanced (atoms/charge don't match): {reaction_formula}")
    dg = cc.standard_dg_prime(reaction)
    return f"{dg.value.magnitude:.2f} +/- {dg.error.magnitude:.2f} {dg.value.units}"


@tool(
    "estimate_reaction_gibbs_energy",
    "Given a biochemical reaction as a KEGG-ID formula (e.g. "
    "'kegg:C00002 + kegg:C00001 = kegg:C00008 + kegg:C00009' for ATP + H2O "
    "-> ADP + Pi), estimate its standard Gibbs free energy change (dG'0, "
    "pH 7, ionic strength 0.25M) via eQuilibrator's Component Contribution "
    "method. Negative dG means thermodynamically favorable in the forward "
    "direction under standard conditions. Complements cobra_fba's flux "
    "balance analysis (FBA says a reaction CAN carry flux at steady "
    "state; this says whether it's energetically favorable to). Never "
    "state a dG value this tool didn't actually return.",
    {"reaction_formula": str},
)
async def estimate_reaction_gibbs_energy(args: dict[str, Any]) -> dict[str, Any]:
    formula = args["reaction_formula"].strip()
    if not formula or "=" not in formula:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "reaction_formula must be a KEGG-ID formula with '=', e.g. "
                    "'kegg:C00002 + kegg:C00001 = kegg:C00008 + kegg:C00009'.",
                }
            ]
        }

    try:
        dg_text = await asyncio.to_thread(_run_dg_prime, formula)
    except Exception as exc:  # noqa: BLE001 -- surfaces parse/lookup errors from eQuilibrator as tool output
        return {"content": [{"type": "text", "text": f"Could not evaluate reaction {formula!r}: {exc}"}]}

    # [equilibrator:reaction] is the citable unit -- real local
    # computation (Component Contribution method against a bundled
    # reference dataset), same methodological-citation convention as
    # cobra_fba.py's [cobra:model_id].
    return {
        "content": [
            {
                "type": "text",
                "text": f"Reaction {formula} [equilibrator:reaction]: standard dG'0 = {dg_text} "
                "(pH 7.0, ionic strength 0.25M)",
            }
        ]
    }


def build_equilibrator_thermo_mcp_server():
    return create_sdk_mcp_server(name="equilibrator_thermo", tools=[estimate_reaction_gibbs_energy])
