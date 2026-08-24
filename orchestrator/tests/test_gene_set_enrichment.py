"""Real tests for app/tools/gene_set_enrichment.py -- no mocking, hits the
live Enrichr REST service on every case here."""
from app.tools.gene_set_enrichment import enrich_gene_set

CANCER_GENES = ["TP53", "BRCA1", "EGFR", "MYC", "KRAS"]


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_breast_cancer_as_top_kegg_term():
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "library": "kegg", "max_results": 3})
    text = await text_of(result)
    assert "[gseapy:KEGG_2021_Human]" in text
    assert "Breast cancer" in text
    assert "adj. p-value" in text


async def test_max_results_clamps_output_count():
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "library": "kegg", "max_results": 2})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) == 2


async def test_max_results_zero_is_floored_to_one_not_defaulted_to_ten():
    # Regression test: max_results=0 is falsy, so "x or 10" would have
    # silently replaced it with the default (10) instead of floor-clamping
    # to 1. Bug found and fixed in app/tools/gene_set_enrichment.py.
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "library": "kegg", "max_results": 0})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) == 1


async def test_max_results_over_25_is_clamped():
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "library": "kegg", "max_results": 999})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) <= 25


async def test_different_library_go_biological_process():
    result = await enrich_gene_set.handler(
        {"genes": CANCER_GENES, "library": "go_biological_process", "max_results": 3}
    )
    text = await text_of(result)
    assert "[gseapy:GO_Biological_Process_2023]" in text


async def test_single_gene_rejected():
    result = await enrich_gene_set.handler({"genes": ["TP53"], "library": "kegg"})
    text = await text_of(result)
    assert "must contain at least 2 gene symbols" in text


async def test_empty_gene_list_rejected():
    result = await enrich_gene_set.handler({"genes": [], "library": "kegg"})
    text = await text_of(result)
    assert "must contain at least 2 gene symbols" in text


async def test_unknown_library_rejected():
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "library": "not_a_real_library"})
    text = await text_of(result)
    assert "Unknown library" in text
    assert "kegg" in text  # error message should list valid choices


async def test_lowercase_gene_symbols_normalized():
    result = await enrich_gene_set.handler(
        {"genes": [g.lower() for g in CANCER_GENES], "library": "kegg", "max_results": 3}
    )
    text = await text_of(result)
    assert "Breast cancer" in text


async def test_default_library_is_kegg():
    result = await enrich_gene_set.handler({"genes": CANCER_GENES, "max_results": 1})
    text = await text_of(result)
    assert "[gseapy:KEGG_2021_Human]" in text
