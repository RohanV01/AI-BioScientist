"""Real tests for app/tools/recount3_search.py -- no mocking, runs the
real Rscript wrapper around recount3 (Bioconductor, see Dockerfile),
which itself hits recount3's real public study catalog. Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass."""
from app.tools.recount3_search import search_recount3_studies


async def text_of(result):
    return result["content"][0]["text"]


async def test_invalid_organism_reports_error():
    result = await search_recount3_studies.handler({"organism": "zebrafish"})
    text = await text_of(result)
    assert "must be one of" in text
