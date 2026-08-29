"""Real tests for app/tools/tcga_clinical.py -- no mocking, runs the
real Rscript wrapper around TCGAbiolinks (Bioconductor, see
Dockerfile), which itself hits the real GDC REST API. Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass, same as cluster_profiler_enrichment."""
from app.tools.tcga_clinical import get_tcga_clinical_data


async def text_of(result):
    return result["content"][0]["text"]


async def test_invalid_project_format_reports_error():
    result = await get_tcga_clinical_data.handler({"project": "not_a_project"})
    text = await text_of(result)
    assert "must look like TCGA-" in text


async def test_empty_project_reports_error():
    result = await get_tcga_clinical_data.handler({"project": ""})
    text = await text_of(result)
    assert "must look like TCGA-" in text
