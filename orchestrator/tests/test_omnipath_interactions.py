"""Real tests for app/tools/omnipath_interactions.py -- no mocking, hits
the real omnipathdb.org REST API."""
from app.tools.omnipath_interactions import get_signaling_interactions


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_interactions():
    result = await get_signaling_interactions.handler({"gene_symbol": "EGFR", "max_results": 5})
    text = await text_of(result)
    assert "OmniPath signaling interactions involving EGFR" in text
    lines = [l for l in text.split("\n") if l.startswith("- ")]
    assert 1 <= len(lines) <= 5


async def test_unknown_gene_reports_not_found():
    result = await get_signaling_interactions.handler({"gene_symbol": "ZZZNOTAREALGENE"})
    text = await text_of(result)
    assert "No OmniPath signaling interactions found" in text


async def test_empty_input_reports_error():
    result = await get_signaling_interactions.handler({"gene_symbol": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
