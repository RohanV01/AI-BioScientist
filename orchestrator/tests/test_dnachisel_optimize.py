"""Real tests for app/tools/dnachisel_optimize.py -- no mocking, runs
the real dnachisel constraint-based DNA optimization engine (verified
live before this file was written)."""
from app.tools.dnachisel_optimize import optimize_codon_usage


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_optimizes_real_sequence():
    sequence = "ATGGCTGATAAAGCTGCTGGTATTCATGGTGGCAAGACCTGA"
    result = await optimize_codon_usage.handler({"sequence": sequence, "species": "e_coli"})
    text = await text_of(result)
    assert "dnachisel" in text
    assert "passed: True" in text


async def test_non_codon_length_reports_error():
    result = await optimize_codon_usage.handler({"sequence": "ATGG", "species": "e_coli"})
    text = await text_of(result)
    assert "multiple of 3" in text


async def test_invalid_species_reports_error():
    sequence = "ATGGCTGATAAAGCTGCTGGTATTCATGGTGGCAAGACCTGA"
    result = await optimize_codon_usage.handler({"sequence": sequence, "species": "martian"})
    text = await text_of(result)
    assert "must be one of" in text


async def test_non_acgt_reports_error():
    result = await optimize_codon_usage.handler({"sequence": "ATGNNN", "species": "e_coli"})
    text = await text_of(result)
    assert "only A/C/G/T" in text
