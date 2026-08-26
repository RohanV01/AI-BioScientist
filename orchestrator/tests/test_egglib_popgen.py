"""Real tests for app/tools/egglib_popgen.py -- no mocking, runs the real
egglib local computation."""
from app.tools.egglib_popgen import compute_diversity_statistics

SEQUENCES = {
    "s1": "ACGTACGTACGTACGTACGT",
    "s2": "ACGTACGAACGTACGTACGT",
    "s3": "ACGTACGTACGTACGAACGT",
    "s4": "ACGTACGTACGTACGTACGA",
}


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_all_statistics():
    result = await compute_diversity_statistics.handler({"sequences": SEQUENCES})
    text = await text_of(result)
    for tag in ["[egglib:S]", "[egglib:Pi]", "[egglib:thetaW]", "[egglib:D]"]:
        assert tag in text


async def test_too_few_sequences_reports_error():
    result = await compute_diversity_statistics.handler({"sequences": {"s1": "ACGT", "s2": "ACGA"}})
    text = await text_of(result)
    assert "at least 3" in text


async def test_mismatched_lengths_reports_error():
    bad = {"s1": "ACGT", "s2": "ACGTA", "s3": "ACGT"}
    result = await compute_diversity_statistics.handler({"sequences": bad})
    text = await text_of(result)
    assert "same length" in text


async def test_identical_sequences_report_zero_diversity():
    identical = {"s1": "ACGTACGT", "s2": "ACGTACGT", "s3": "ACGTACGT"}
    result = await compute_diversity_statistics.handler({"sequences": identical})
    text = await text_of(result)
    assert "[egglib:S]: 0" in text
