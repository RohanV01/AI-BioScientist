"""Real tests for app/tools/ontologies.py -- no mocking, hits the real
EBI Ontology Lookup Service (OLS) API."""
from app.tools.ontologies import search_ontology_term


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_resolves_real_term():
    result = await search_ontology_term.handler({"query": "seizure", "ontology": "hp"})
    text = await text_of(result)
    assert "HP:" in text


async def test_search_without_ontology_filter():
    result = await search_ontology_term.handler({"query": "breast cancer"})
    text = await text_of(result)
    assert text.strip()
    assert "-" in text  # at least one result line


async def test_mondo_disease_search():
    result = await search_ontology_term.handler({"query": "Noonan syndrome", "ontology": "mondo"})
    text = await text_of(result)
    assert "MONDO:" in text


async def test_max_results_clamped_to_fifteen():
    result = await search_ontology_term.handler({"query": "cell", "max_results": 999})
    lines = [l for l in (await text_of(result)).split("\n") if l.startswith("- ")]
    assert len(lines) <= 15


async def test_nonsense_query_returns_no_terms_gracefully():
    result = await search_ontology_term.handler({"query": "zzzznonexistentontologyterm98765xyz"})
    text = await text_of(result)
    assert "No ontology terms found" in text
