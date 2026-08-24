"""Real tests for app/tools/cobra_fba.py -- no mocking, hits the real
BiGG Models API and runs actual cobrapy FBA on a downloaded model."""
from app.tools.cobra_fba import run_flux_balance_analysis, search_metabolic_models


async def text_of(result):
    return result["content"][0]["text"]


async def test_search_happy_path_returns_real_models():
    result = await search_metabolic_models.handler({"organism_query": "Escherichia coli"})
    text = await text_of(result)
    assert "BiGG model" in text
    assert "reactions" in text


async def test_search_default_max_results_is_five():
    result = await search_metabolic_models.handler({"organism_query": "coli"})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- BiGG model")]
    assert 1 <= len(lines) <= 5


async def test_search_max_results_clamped_to_twenty():
    result = await search_metabolic_models.handler({"organism_query": "coli", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- BiGG model")]
    assert len(lines) <= 20


async def test_search_nonsense_query_reports_no_models():
    result = await search_metabolic_models.handler({"organism_query": "zzznotarealorganism9999"})
    text = await text_of(result)
    assert "No BiGG models found" in text


async def test_fba_happy_path_on_ecoli_core():
    # e_coli_core is BiGG's canonical small textbook model -- fast to
    # download and optimize, real FBA end to end.
    result = await run_flux_balance_analysis.handler({"bigg_model_id": "e_coli_core", "top_n_fluxes": 3})
    text = await text_of(result)
    assert "e_coli_core" in text
    assert "Predicted optimal growth rate" in text
    assert "[cobra:e_coli_core]" in text
    assert "Top 3 reactions by absolute flux" in text


async def test_fba_nonexistent_model_id_reports_not_found():
    result = await run_flux_balance_analysis.handler({"bigg_model_id": "zzznotarealmodel9999"})
    text = await text_of(result)
    assert "No BiGG model found" in text


async def test_fba_top_n_fluxes_clamped_to_twenty():
    result = await run_flux_balance_analysis.handler({"bigg_model_id": "e_coli_core", "top_n_fluxes": 999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- ") and "flux" in l]
    assert len(lines) <= 20
