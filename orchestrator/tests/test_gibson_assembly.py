"""Real tests for app/tools/gibson_assembly.py -- no mocking, runs the
real pydna Gibson assembly engine."""
from app.tools.gibson_assembly import simulate_gibson_assembly

FRAG1 = "ATGCATGCATGCATGCATGCTTTTGGGGCCCCAAAA"
FRAG2 = "GGGGCCCCAAAAGGGGTTTTCCCCAAAAGGGGCCCC"
FRAG3 = "GGGGTTTTCCCCAAAAGGGGCCCCATGCATGCATGCATGCATGC"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_real_assembly_product():
    result = await simulate_gibson_assembly.handler({"fragments": [FRAG1, FRAG2, FRAG3], "min_overlap": 8})
    text = await text_of(result)
    assert "pydna" in text
    assert "product" in text
    assert "bp" in text


async def test_too_few_fragments_reports_error():
    result = await simulate_gibson_assembly.handler({"fragments": [FRAG1]})
    text = await text_of(result)
    assert "at least 2" in text


async def test_invalid_sequence_reports_error():
    result = await simulate_gibson_assembly.handler({"fragments": [FRAG1, "NOTDNA123"]})
    text = await text_of(result)
    assert "only A/C/G/T" in text


async def test_non_overlapping_fragments_report_no_product():
    result = await simulate_gibson_assembly.handler(
        {"fragments": ["ATGCATGCATGCATGCATGC", "TTTTCCCCGGGGAAAATTTT"], "min_overlap": 15}
    )
    text = await text_of(result)
    assert "No valid Gibson assembly product" in text
