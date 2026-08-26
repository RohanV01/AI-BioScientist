"""Real tests for app/tools/minimap2_align.py -- no mocking, runs the
real minimap2 (mappy) aligner."""
import random

from app.tools.minimap2_align import align_to_reference

random.seed(42)
REFERENCE = "".join(random.choice("ACGT") for _ in range(2000))
QUERY = REFERENCE[500:700]


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_the_real_mapping_location():
    result = await align_to_reference.handler({"reference": REFERENCE, "query": QUERY, "preset": "map-ont"})
    text = await text_of(result)
    assert "reference 500-700" in text


async def test_default_preset_is_map_ont():
    result = await align_to_reference.handler({"reference": REFERENCE, "query": QUERY})
    text = await text_of(result)
    assert "map-ont" in text


async def test_unrelated_query_reports_no_alignment():
    unrelated = "".join(random.choice("ACGT") for _ in range(150))
    result = await align_to_reference.handler({"reference": REFERENCE, "query": unrelated})
    text = await text_of(result)
    assert "No alignment found" in text or "reference" in text


async def test_invalid_preset_reports_error():
    result = await align_to_reference.handler({"reference": REFERENCE, "query": QUERY, "preset": "not_a_preset"})
    text = await text_of(result)
    assert "preset must be one of" in text


async def test_empty_input_reports_error():
    result = await align_to_reference.handler({"reference": "", "query": QUERY})
    text = await text_of(result)
    assert "must be non-empty" in text
