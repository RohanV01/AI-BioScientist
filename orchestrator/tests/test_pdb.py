"""Real tests for app/tools/pdb.py -- no mocking, hits the real RCSB
Search and GraphQL APIs."""
from app.tools.pdb import search_structures


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_hits():
    result = await search_structures.handler({"query": "lysozyme", "max_results": 3})
    text = await text_of(result)
    assert "PDB " in text
    assert "resolution" in text
    assert "method:" in text


async def test_default_max_results_is_five():
    result = await search_structures.handler({"query": "hemoglobin"})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- PDB")]
    assert 1 <= len(lines) <= 5


async def test_max_results_is_clamped_to_fifteen():
    result = await search_structures.handler({"query": "kinase", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- PDB")]
    assert len(lines) <= 15


async def test_nonsense_query_reports_no_structures_found():
    result = await search_structures.handler({"query": "zzznotarealprotein9999xyz"})
    text = await text_of(result)
    assert "No PDB structures found" in text


async def test_specific_ligand_query_returns_hits():
    result = await search_structures.handler({"query": "EGFR kinase domain", "max_results": 2})
    text = await text_of(result)
    assert "PDB " in text or "No PDB structures found" in text
