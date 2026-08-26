"""Real tests for app/tools/mummer_align.py -- no mocking, runs the
real nucmer/show-coords CLI (apt mummer package, present in the Docker
image)."""
from app.tools.mummer_align import mummer_align

REF = "ATGGCGCATTACGATCGATCGATCGATCGATCGATCGGCGCATTACGATCGATGGCGCATTACGATCGATCGATCGATCGATCGATCGGCGCATTACGATCG" * 3
QUERY = REF


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_real_match():
    result = await mummer_align.handler({"reference_sequence": REF, "query_sequence": QUERY})
    text = await text_of(result)
    assert "MUMmer4" in text
    assert "identity" in text


async def test_missing_reference_reports_error():
    result = await mummer_align.handler({"reference_sequence": "", "query_sequence": "ATGC"})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_query_reports_error():
    result = await mummer_align.handler({"reference_sequence": "ATGC", "query_sequence": ""})
    text = await text_of(result)
    assert "must both be non-empty" in text
