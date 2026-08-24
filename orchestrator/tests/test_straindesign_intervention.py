"""Real tests for app/tools/straindesign_intervention.py -- no mocking,
a real BiGG model fetch and a real OptKnock MILP solve run on the
happy-path case. e_coli_core is the smallest standard BiGG model, so
this is the fastest real case that still exercises the full pipeline."""
from app.tools.straindesign_intervention import design_strain_intervention

MODEL = "e_coli_core"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_optknock_finds_and_verifies_knockouts():
    result = await design_strain_intervention.handler(
        {"bigg_model_id": MODEL, "target_reaction_id": "EX_succ_e", "max_interventions": 3}
    )
    text = await text_of(result)
    assert "[straindesign:e_coli_core]" in text
    assert "Proposed knockout(s):" in text
    assert "Independently re-verified" in text


async def test_nonexistent_model_reports_not_found():
    result = await design_strain_intervention.handler(
        {"bigg_model_id": "not_a_real_bigg_model_xyz", "target_reaction_id": "EX_succ_e"}
    )
    text = await text_of(result)
    assert "No BiGG model found" in text


async def test_nonexistent_reaction_reports_not_found():
    result = await design_strain_intervention.handler(
        {"bigg_model_id": MODEL, "target_reaction_id": "NOT_A_REAL_REACTION_ID"}
    )
    text = await text_of(result)
    assert "not found in model" in text


async def test_max_interventions_clamped_to_six():
    # A generous max_interventions (20) should be silently clamped to 6,
    # not passed through to the MILP solver as-is -- confirm it runs
    # (doesn't error on the raw value) rather than asserting solver internals.
    result = await design_strain_intervention.handler(
        {"bigg_model_id": MODEL, "target_reaction_id": "EX_succ_e", "max_interventions": 20, "max_solutions_hint": 1}
    )
    text = await text_of(result)
    assert "straindesign:" in text or "No intervention set found" in text
