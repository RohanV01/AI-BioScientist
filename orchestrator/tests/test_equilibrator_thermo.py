"""Real tests for app/tools/equilibrator_thermo.py -- no mocking, the
actual Component Contribution method runs against its bundled
reference dataset on every case here."""
from app.tools.equilibrator_thermo import estimate_reaction_gibbs_energy

ATP_HYDROLYSIS = "kegg:C00002 + kegg:C00001 = kegg:C00008 + kegg:C00009"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_atp_hydrolysis_is_favorable():
    result = await estimate_reaction_gibbs_energy.handler({"reaction_formula": ATP_HYDROLYSIS})
    text = await text_of(result)
    assert "[equilibrator:reaction]" in text
    assert "standard dG'0" in text
    assert "joule" in text.lower()
    # ATP hydrolysis is a textbook thermodynamically favorable reaction.
    assert "-29." in text or "-30." in text


async def test_empty_formula_rejected():
    result = await estimate_reaction_gibbs_energy.handler({"reaction_formula": ""})
    text = await text_of(result)
    assert "must be a KEGG-ID formula" in text


async def test_formula_missing_equals_rejected():
    result = await estimate_reaction_gibbs_energy.handler({"reaction_formula": "kegg:C00002 + kegg:C00001"})
    text = await text_of(result)
    assert "must be a KEGG-ID formula" in text


async def test_unbalanced_reaction_reports_error_not_crash():
    # C00002 (ATP) alone on both sides of "=" with mismatched stoichiometry
    # relative to a real balanced hydrolysis -- exercises the
    # is_balanced() rejection path without raising.
    result = await estimate_reaction_gibbs_energy.handler(
        {"reaction_formula": "kegg:C00002 = kegg:C00008"}
    )
    text = await text_of(result)
    assert "Could not evaluate reaction" in text or "not balanced" in text.lower()


async def test_unknown_compound_id_reports_error_not_crash():
    result = await estimate_reaction_gibbs_energy.handler(
        {"reaction_formula": "kegg:C99999 = kegg:C00001"}
    )
    text = await text_of(result)
    assert "Could not evaluate reaction" in text
