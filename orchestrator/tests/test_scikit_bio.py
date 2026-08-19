"""Real tests for app/tools/scikit_bio.py -- no mocking, scikit-bio's
actual alpha_diversity runs on every case here (in-process, no network)."""
from app.tools.scikit_bio import compute_diversity_metrics


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_all_default_metrics():
    result = await compute_diversity_metrics.handler({"counts": [10, 5, 0, 3, 2]})
    text = await text_of(result)
    assert "Shannon diversity index" in text
    assert "Simpson diversity index" in text
    assert "Observed species richness" in text
    assert "[scikit-bio:shannon]" in text
    assert "Present taxa:" in text


async def test_specific_metric_subset():
    result = await compute_diversity_metrics.handler({"counts": [10, 5, 3], "metrics": ["richness"]})
    text = await text_of(result)
    assert "Observed species richness" in text
    assert "Shannon" not in text


async def test_custom_taxon_labels_are_used():
    result = await compute_diversity_metrics.handler(
        {"counts": [7, 0, 2], "taxon_labels": ["E.coli", "Salmonella", "Bacteroides"]}
    )
    text = await text_of(result)
    assert "E.coli (7)" in text
    assert "Bacteroides (2)" in text
    assert "Salmonella" not in text  # zero-count taxa excluded from "present taxa"


async def test_all_zero_counts_rejected():
    result = await compute_diversity_metrics.handler({"counts": [0, 0, 0]})
    text = await text_of(result)
    assert "at least one nonzero" in text


async def test_empty_counts_rejected():
    result = await compute_diversity_metrics.handler({"counts": []})
    text = await text_of(result)
    assert "at least one nonzero" in text


async def test_mismatched_labels_length_rejected():
    result = await compute_diversity_metrics.handler({"counts": [1, 2, 3], "taxon_labels": ["a", "b"]})
    text = await text_of(result)
    assert "same length as counts" in text


async def test_unknown_metric_rejected():
    result = await compute_diversity_metrics.handler({"counts": [1, 2, 3], "metrics": ["not_a_real_metric"]})
    text = await text_of(result)
    assert "Unknown metric" in text


async def test_single_taxon_perfectly_uneven():
    # One taxon holding all the abundance -- minimum possible diversity,
    # exercises the boundary rather than a mid-range value.
    result = await compute_diversity_metrics.handler({"counts": [42]})
    text = await text_of(result)
    assert "0.0000" in text  # Shannon and Simpson are both 0 for a single taxon
