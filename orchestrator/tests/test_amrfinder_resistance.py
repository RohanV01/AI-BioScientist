"""Real tests for app/tools/amrfinder_resistance.py -- no mocking, runs
the real amrfinder binary (NCBI's own prebuilt release, see Dockerfile)
against the real database fetched via amrfinder_update at build time.
Not locally testable in this sandbox (the DB fetch is a build-time
Docker image step) -- validation-path tests run directly; the
happy-path run is deferred to the batch Docker build/test pass."""
from app.tools.amrfinder_resistance import detect_resistance_genes


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await detect_resistance_genes.handler({"sequence": "ACGT" * 5, "is_nucleotide": True})
    text = await text_of(result)
    assert "at least 50" in text


async def test_invalid_nucleotide_characters_reports_error():
    result = await detect_resistance_genes.handler({"sequence": "ACGTZ" * 20, "is_nucleotide": True})
    text = await text_of(result)
    assert "invalid" in text


async def test_invalid_protein_characters_reports_error():
    result = await detect_resistance_genes.handler({"sequence": "MKTZZZ" * 20, "is_nucleotide": False})
    text = await text_of(result)
    assert "invalid" in text
