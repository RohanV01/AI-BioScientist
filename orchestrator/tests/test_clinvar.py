"""Real tests for app/tools/clinvar.py -- no mocking, hits the real NCBI
ClinVar E-utilities API."""
from app.tools.clinvar import search_variants


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_variants():
    result = await search_variants.handler({"gene": "BRCA1", "max_results": 3})
    text = await text_of(result)
    assert "ClinVar" in text
    assert "classification:" in text


async def test_term_filter_narrows_query():
    result = await search_variants.handler({"gene": "BRCA1", "term": "pathogenic", "max_results": 3})
    text = await text_of(result)
    assert "ClinVar" in text


async def test_nonexistent_gene_reports_no_variants_gracefully():
    result = await search_variants.handler({"gene": "ZZZNOTAREALGENE123"})
    text = await text_of(result)
    assert "No ClinVar variants found" in text


async def test_max_results_clamped_to_twenty():
    result = await search_variants.handler({"gene": "TP53", "max_results": 999})
    lines = [l for l in (await text_of(result)).split("\n") if l.startswith("- ClinVar")]
    assert len(lines) <= 20
