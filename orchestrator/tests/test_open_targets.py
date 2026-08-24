"""Real tests for app/tools/open_targets.py -- no mocking, hits the
live Open Targets GraphQL API on every case here."""
from app.tools.open_targets import get_target_disease_associations, search_entities


async def text_of(result):
    return result["content"][0]["text"]


async def test_search_entities_finds_egfr():
    result = await search_entities.handler({"query": "EGFR", "max_results": 5})
    text = await text_of(result)
    assert "ENSG00000146648" in text


async def test_search_entities_nonsense_query_returns_no_results_gracefully():
    result = await search_entities.handler({"query": "zzqxnotarealgenexyz123", "max_results": 5})
    text = await text_of(result)
    assert "No Open Targets entities found" in text


async def test_get_target_disease_associations_for_egfr():
    result = await get_target_disease_associations.handler(
        {"ensembl_id": "ENSG00000146648", "max_results": 10}
    )
    text = await text_of(result)
    assert "EGFR" in text
    assert "ENSG00000146648" in text
    assert "association score" in text


async def test_get_target_disease_associations_invalid_id_returns_no_results_gracefully():
    result = await get_target_disease_associations.handler(
        {"ensembl_id": "ENSGNOTAREALID999999", "max_results": 5}
    )
    text = await text_of(result)
    assert "No Open Targets record found" in text
