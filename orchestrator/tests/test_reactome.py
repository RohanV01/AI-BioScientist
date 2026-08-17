"""Real tests for app/tools/reactome.py -- no mocking, hits the live
Reactome Content Service API on every case here."""
from app.tools.reactome import search_pathways


async def text_of(result):
    return result["content"][0]["text"]


async def test_search_pathways_for_egfr():
    result = await search_pathways.handler({"query": "EGFR", "max_results": 5})
    text = await text_of(result)
    assert "Reactome" in text
    assert "R-HSA-" in text


async def test_search_pathways_respects_max_results_cap():
    result = await search_pathways.handler({"query": "signaling", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.splitlines() if l.startswith("- Reactome")]
    assert len(lines) <= 15


async def test_search_pathways_nonsense_query_returns_404_gracefully():
    result = await search_pathways.handler({"query": "zzqxnonexistentpathwayxyz123", "max_results": 5})
    text = await text_of(result)
    assert "No Reactome pathways found" in text


async def test_search_pathways_custom_species():
    result = await search_pathways.handler({"query": "Egfr", "species": "Mus musculus", "max_results": 5})
    text = await text_of(result)
    # Either real mouse pathways come back, or a clean "no results" -- never a crash.
    assert "Reactome" in text or "No Reactome pathways found" in text
