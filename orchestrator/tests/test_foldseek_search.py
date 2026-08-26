"""Real tests for app/tools/foldseek_search.py -- no mocking, fetches
real PDB structures and runs the real foldseek CLI (downloaded as a
static binary, see Dockerfile)."""
from app.tools.foldseek_search import foldseek_search


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_structural_hit():
    result = await foldseek_search.handler({"query_pdb_id": "1CRN", "target_pdb_ids": ["1CRN"]})
    text = await text_of(result)
    assert "Foldseek" in text
    assert "1CRN" in text


async def test_empty_query_reports_error():
    result = await foldseek_search.handler({"query_pdb_id": "", "target_pdb_ids": ["1CRN"]})
    text = await text_of(result)
    assert "must not be empty" in text


async def test_empty_targets_reports_error():
    result = await foldseek_search.handler({"query_pdb_id": "1CRN", "target_pdb_ids": []})
    text = await text_of(result)
    assert "non-empty list" in text


async def test_unknown_query_reports_not_found():
    result = await foldseek_search.handler({"query_pdb_id": "ZZZZ", "target_pdb_ids": ["1CRN"]})
    text = await text_of(result)
    assert "No PDB entry found for query" in text
