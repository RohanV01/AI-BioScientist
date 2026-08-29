"""Real tests for app/tools/prokka_annotate.py -- no mocking, runs the
real prokka binary (apt package, see Dockerfile; its real
`tbl2asn`-discontinuation gotcha and fix are documented there and in
the tool's own module docstring). Prokka's own multi-minute pipeline
isn't practical to run in this sandbox's test setup -- validation-path
tests run directly; the happy-path run is deferred to the batch Docker
build/test pass, same as orthofinder_groups above."""
from app.tools.prokka_annotate import annotate_genome_prokka


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await annotate_genome_prokka.handler({"sequence": "ACGT" * 10})
    text = await text_of(result)
    assert "at least 200bp" in text


async def test_invalid_characters_reports_error():
    result = await annotate_genome_prokka.handler({"sequence": "ACGTX" * 60})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
