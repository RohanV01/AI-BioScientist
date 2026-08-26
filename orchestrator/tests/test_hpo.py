"""Real tests for app/tools/hpo.py -- no mocking, hits the real HPO
(ontology.jax.org) REST API."""
from app.tools.hpo import get_phenotype_diseases


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_with_hpo_id():
    result = await get_phenotype_diseases.handler({"phenotype": "HP:0001250", "max_results": 5})
    text = await text_of(result)
    assert "HPO term HP:0001250" in text
    lines = [l for l in text.split("\n") if l.startswith("- ")]
    assert 1 <= len(lines) <= 5


async def test_happy_path_with_free_text():
    result = await get_phenotype_diseases.handler({"phenotype": "seizure", "max_results": 3})
    text = await text_of(result)
    assert "resolved from 'seizure'" in text


async def test_nonsense_phenotype_reports_no_term_found():
    result = await get_phenotype_diseases.handler({"phenotype": "zzznotarealphenotype9999xyz"})
    text = await text_of(result)
    assert "No HPO term found" in text


async def test_empty_input_reports_error():
    result = await get_phenotype_diseases.handler({"phenotype": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
