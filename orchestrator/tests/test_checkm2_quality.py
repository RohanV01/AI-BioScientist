"""Real tests for app/tools/checkm2_quality.py -- no mocking, runs the
real checkm2 CLI against the real baked-in DIAMOND database (see
Dockerfile). Not locally testable in this sandbox (the database is a
~1.7GB build-time Docker image asset) -- validation-path tests run
directly; the happy-path run is deferred to the batch Docker build/
test pass."""
from app.tools.checkm2_quality import assess_genome_quality


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await assess_genome_quality.handler({"sequence": "ACGT" * 100})
    text = await text_of(result)
    assert "at least 5000bp" in text


async def test_invalid_characters_reports_error():
    result = await assess_genome_quality.handler({"sequence": "ACGTX" * 2000})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
