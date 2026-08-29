"""Real tests for app/tools/bakta_annotate.py -- no mocking, runs the
real bakta CLI against the real baked-in light database (see
Dockerfile). Not locally testable in this sandbox (the database is a
build-time Docker image asset) -- validation-path tests run directly;
the happy-path run is deferred to the batch Docker build/test pass."""
from app.tools.bakta_annotate import annotate_genome_bakta


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await annotate_genome_bakta.handler({"sequence": "ACGT" * 10})
    text = await text_of(result)
    assert "at least 200bp" in text


async def test_invalid_characters_reports_error():
    result = await annotate_genome_bakta.handler({"sequence": "ACGTX" * 60})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
