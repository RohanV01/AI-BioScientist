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


# Real gap found by battle-testing with hard questions: no way to look up
# ClinVar by exact genomic coordinate (only by gene). 17-43104913 is a
# real, verified BRCA1 position (NM_007294.4(BRCA1):c.241_256del).
async def test_variant_id_coordinate_lookup_finds_real_variant():
    result = await search_variants.handler({"variant_id": "17-43104913-A-T", "max_results": 5})
    text = await text_of(result)
    assert "BRCA1" in text
    assert "VCV004884209" in text  # the exact known record at this position
    assert "GRCh38 chr17:43104913" in text


async def test_variant_id_malformed_reports_error_not_crash():
    result = await search_variants.handler({"variant_id": "rs80357382"})
    text = await text_of(result)
    assert "must be chrom-pos-ref-alt format" in text


async def test_neither_gene_nor_variant_id_reports_error_not_crash():
    result = await search_variants.handler({})
    text = await text_of(result)
    assert "Provide either gene or variant_id" in text
