"""Real tests for app/tools/poolfstat_fst.py -- no mocking, runs the
real Rscript wrapper around poolfstat (CRAN, see Dockerfile). Not
locally testable in this sandbox (no R interpreter available) --
validation-path tests run directly; the happy-path run is deferred to
the batch Docker build/test pass, same as cluster_profiler_enrichment."""
from app.tools.poolfstat_fst import compute_pool_fst


async def text_of(result):
    return result["content"][0]["text"]


async def test_too_few_populations_reports_error():
    populations = {"pop_a": {"snp1": [10, 20]}}
    result = await compute_pool_fst.handler({"populations": populations})
    text = await text_of(result)
    assert "at least 2" in text


async def test_mismatched_snp_sets_reports_error():
    populations = {
        "pop_a": {"snp1": [10, 20], "snp2": [5, 20]},
        "pop_b": {"snp1": [15, 20]},
    }
    result = await compute_pool_fst.handler({"populations": populations})
    text = await text_of(result)
    assert "exact same set of SNP ids" in text


async def test_ref_exceeds_total_reports_error():
    populations = {
        "pop_a": {"snp1": [25, 20]},
        "pop_b": {"snp1": [15, 20]},
    }
    result = await compute_pool_fst.handler({"populations": populations})
    text = await text_of(result)
    assert "cannot exceed total_count" in text
