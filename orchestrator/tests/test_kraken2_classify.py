"""Real tests for app/tools/kraken2_classify.py -- no mocking, runs the
real kraken2 binary against the real baked-in k2_viral database (see
Dockerfile). Not locally testable in this sandbox (the database is a
build-time Docker image asset) -- validation-path tests run directly;
the happy-path run is deferred to the batch Docker build/test pass,
same as orthofinder_groups/treemix_population_tree above."""
from app.tools.kraken2_classify import classify_sequence_kraken2


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await classify_sequence_kraken2.handler({"sequence": "ACGT" * 5})
    text = await text_of(result)
    assert "at least 50bp" in text


async def test_invalid_characters_reports_error():
    result = await classify_sequence_kraken2.handler({"sequence": "ACGTX" * 20})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
