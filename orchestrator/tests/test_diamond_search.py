"""Real tests for app/tools/diamond_search.py -- no mocking, runs the
real diamond CLI (downloaded as a static binary, see Dockerfile)."""
from app.tools.diamond_search import diamond_search

QUERY = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
EXACT = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
UNRELATED = "GGGGWWWWKKKKPPPPLLLLIIIIVVVVFFFFYYYYNNNNQQQQSSSSTTTTCCCC"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_exact_match():
    result = await diamond_search.handler(
        {"query_sequence": QUERY, "reference_sequences": {"exact": EXACT, "unrelated": UNRELATED}}
    )
    text = await text_of(result)
    assert "DIAMOND" in text
    assert "exact" in text


async def test_empty_query_reports_error():
    result = await diamond_search.handler({"query_sequence": "", "reference_sequences": {"a": "MKT"}})
    text = await text_of(result)
    assert "must not be empty" in text


async def test_empty_references_reports_error():
    result = await diamond_search.handler({"query_sequence": QUERY, "reference_sequences": {}})
    text = await text_of(result)
    assert "non-empty dict" in text
