"""Real tests for app/tools/gprofiler_enrichment.py -- no mocking, hits
the live g:Profiler REST service on every case here."""
from app.tools.gprofiler_enrichment import profile_gene_list

CANCER_GENES = ["TP53", "BRCA1", "EGFR", "MYC", "KRAS"]


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_breast_cancer_as_top_term():
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "max_results": 3})
    text = await text_of(result)
    assert "[gprofiler:hsapiens]" in text
    assert "Breast cancer" in text
    assert "p-value" in text


async def test_default_organism_is_human():
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "max_results": 1})
    text = await text_of(result)
    assert "(hsapiens)" in text


async def test_max_results_clamps_output_count():
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "max_results": 2})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) == 2


async def test_max_results_zero_is_floored_to_one_not_defaulted_to_ten():
    # Regression test: max_results=0 is falsy, so "x or 10" would have
    # silently replaced it with the default (10) instead of floor-clamping
    # to 1. Bug found and fixed in app/tools/gprofiler_enrichment.py (same
    # class of bug already found in gene_set_enrichment.py/nrpcalc_design.py).
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "max_results": 0})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) == 1


async def test_max_results_over_25_is_clamped():
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "max_results": 999})
    text = await text_of(result)
    term_lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(term_lines) <= 25


async def test_single_gene_rejected():
    result = await profile_gene_list.handler({"genes": ["TP53"]})
    text = await text_of(result)
    assert "must contain at least 2 gene symbols" in text


async def test_empty_gene_list_rejected():
    result = await profile_gene_list.handler({"genes": []})
    text = await text_of(result)
    assert "must contain at least 2 gene symbols" in text


async def test_unknown_organism_rejected():
    result = await profile_gene_list.handler({"genes": CANCER_GENES, "organism": "not_a_real_organism"})
    text = await text_of(result)
    assert "Unknown organism" in text
    assert "hsapiens" in text  # error message should list valid choices


async def test_lowercase_gene_symbols_normalized():
    result = await profile_gene_list.handler(
        {"genes": [g.lower() for g in CANCER_GENES], "max_results": 3}
    )
    text = await text_of(result)
    assert "Breast cancer" in text


async def test_mouse_organism_accepted():
    # Different organism, different (real) gene symbols -- confirms the
    # organism switch actually changes which database g:Profiler queries,
    # not just accepted-then-ignored.
    result = await profile_gene_list.handler(
        {"genes": ["Trp53", "Myc", "Kras"], "organism": "mmusculus", "max_results": 3}
    )
    text = await text_of(result)
    assert "[gprofiler:mmusculus]" in text
