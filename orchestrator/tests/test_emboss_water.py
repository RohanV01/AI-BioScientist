"""Real tests for app/tools/emboss_water.py -- no mocking, runs the
real EMBOSS water CLI (apt emboss package, present in the Docker image)."""
from app.tools.emboss_water import water_local_alignment


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_identical_sequences_are_100_percent():
    seq = "ATGGCGCATTACGATCGATCGATCGATCGATCGATCGGCGCATTACGATCG"
    result = await water_local_alignment.handler({"sequence_a": seq, "sequence_b": seq})
    text = await text_of(result)
    assert "EMBOSS water" in text
    assert "100.0%" in text


async def test_missing_sequence_a_reports_error():
    result = await water_local_alignment.handler({"sequence_a": "", "sequence_b": "ATGC"})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_sequence_b_reports_error():
    result = await water_local_alignment.handler({"sequence_a": "ATGC", "sequence_b": ""})
    text = await text_of(result)
    assert "must both be non-empty" in text
