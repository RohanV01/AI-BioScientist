"""Real tests for app/tools/wgcna_modules.py -- no mocking, runs the
real Rscript wrapper around WGCNA (CRAN, see Dockerfile). Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass, same as cluster_profiler_enrichment."""
from app.tools.wgcna_modules import detect_coexpression_modules


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_few_genes_reports_error():
    expression = {f"gene{i}": [1.0, 2.0, 3.0, 4.0] for i in range(5)}
    result = await detect_coexpression_modules.handler({"expression": expression})
    text = await text_of(result)
    assert "at least 20" in text


async def test_too_few_samples_reports_error():
    expression = {f"gene{i}": [1.0, 2.0] for i in range(25)}
    result = await detect_coexpression_modules.handler({"expression": expression})
    text = await text_of(result)
    assert "at least 4 samples" in text


async def test_mismatched_sample_counts_reports_error():
    expression = {f"gene{i}": [1.0, 2.0, 3.0, 4.0] for i in range(24)}
    expression["gene_bad"] = [1.0, 2.0]
    result = await detect_coexpression_modules.handler({"expression": expression})
    text = await text_of(result)
    assert "same number of sample values" in text
