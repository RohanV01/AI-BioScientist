"""Real tests for app/tools/europepmc.py -- no mocking, hits the real
Europe PMC REST API."""
from app.tools.europepmc import search_europepmc


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_results():
    result = await search_europepmc.handler({"query": "BRCA1 breast cancer", "max_results": 3})
    text = await text_of(result)
    assert "Europe PMC results" in text
    lines = [l for l in text.split("\n") if l.startswith("- [")]
    assert 1 <= len(lines) <= 3


async def test_default_max_results_is_five():
    result = await search_europepmc.handler({"query": "CRISPR"})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- [")]
    assert 1 <= len(lines) <= 5


async def test_max_results_is_clamped_to_twenty():
    result = await search_europepmc.handler({"query": "cancer", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- [")]
    assert len(lines) <= 20


async def test_empty_query_reports_error():
    result = await search_europepmc.handler({"query": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
