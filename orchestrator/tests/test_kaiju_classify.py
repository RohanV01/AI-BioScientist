"""Real tests for app/tools/kaiju_classify.py -- no mocking, runs the
real kaiju binary (compiled from source, see Dockerfile) against the
real baked-in kaiju_db_viruses database. Not locally testable in this
sandbox (kaiju must be compiled and the database is a build-time
Docker image asset -- its real internal file names, names.dmp/
nodes.dmp/kaiju_db_viruses.fmi, were confirmed live by partially
downloading the real release tarball's listing) -- validation-path
tests run directly; the happy-path run is deferred to the batch Docker
build/test pass."""
from app.tools.kaiju_classify import classify_sequence_kaiju


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_short_reports_error():
    result = await classify_sequence_kaiju.handler({"sequence": "ACGT" * 5})
    text = await text_of(result)
    assert "at least 50bp" in text


async def test_invalid_characters_reports_error():
    result = await classify_sequence_kaiju.handler({"sequence": "ACGTX" * 20})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
