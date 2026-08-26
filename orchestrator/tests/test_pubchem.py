"""Real tests for app/tools/pubchem.py -- no mocking, hits the real
PubChem PUG-REST API."""
from app.tools.pubchem import search_compound


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_compound():
    result = await search_compound.handler({"name": "aspirin"})
    text = await text_of(result)
    assert "PubChem CID 2244" in text
    assert "C9H8O4" in text


async def test_nonsense_name_reports_not_found():
    result = await search_compound.handler({"name": "zzznotarealcompound9999xyz"})
    text = await text_of(result)
    assert "No PubChem compound found" in text


async def test_empty_name_reports_error():
    result = await search_compound.handler({"name": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
