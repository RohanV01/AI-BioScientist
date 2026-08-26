"""Real tests for app/tools/gwas_catalog.py -- no mocking, hits the real
NHGRI-EBI GWAS Catalog API. Genuinely slow (60-180s per call, confirmed
live) -- expected, not a bug."""
from app.tools.gwas_catalog import get_gwas_studies_for_variant


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_studies():
    result = await get_gwas_studies_for_variant.handler({"variant_id": "rs7412", "max_results": 5})
    text = await text_of(result)
    assert "GWAS Catalog" in text
    assert "study GCST" in text
    assert "PMID" in text


async def test_invalid_variant_id_reports_error():
    result = await get_gwas_studies_for_variant.handler({"variant_id": "not-a-variant"})
    text = await text_of(result)
    assert "real dbSNP rsID" in text
