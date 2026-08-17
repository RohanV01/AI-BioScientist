"""Real tests for app/tools/chembl.py -- no mocking, hits the live
ChEMBL REST API on every case here."""
from app.tools.chembl import compound_search, get_bioactivity


async def text_of(result):
    return result["content"][0]["text"]


async def test_compound_search_finds_imatinib():
    result = await compound_search.handler({"query": "imatinib", "max_results": 5})
    text = await text_of(result)
    assert "CHEMBL941" in text
    assert "ChEMBL ID" in text


async def test_compound_search_respects_max_results_cap():
    result = await compound_search.handler({"query": "aspirin", "max_results": 999})
    text = await text_of(result)
    # Must not error on an absurd max_results -- clamped to <=20 internally.
    lines = [l for l in text.splitlines() if l.startswith("- ChEMBL ID")]
    assert len(lines) <= 20


async def test_compound_search_nonsense_query_returns_no_results_gracefully():
    result = await compound_search.handler({"query": "zzqxnonexistentcompoundxyz123", "max_results": 5})
    text = await text_of(result)
    assert "No ChEMBL compounds found" in text


async def test_get_bioactivity_for_imatinib():
    result = await get_bioactivity.handler({"chembl_id": "CHEMBL941", "max_results": 10})
    text = await text_of(result)
    assert "CHEMBL941" in text
    assert "Target" in text


async def test_get_bioactivity_invalid_id_returns_no_results_gracefully():
    result = await get_bioactivity.handler({"chembl_id": "CHEMBLNOTREAL999999", "max_results": 5})
    text = await text_of(result)
    assert "No bioactivity records found" in text
