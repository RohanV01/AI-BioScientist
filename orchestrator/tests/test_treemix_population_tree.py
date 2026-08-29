"""Real tests for app/tools/treemix_population_tree.py -- no mocking,
runs the real treemix binary (compiled from source, see Dockerfile)."""
from app.tools.treemix_population_tree import build_population_tree


async def text_of(result):
    return result["content"][0]["text"]


def _counts(*pairs):
    return [list(p) for p in pairs]


async def test_happy_path_builds_real_tree():
    populations = {
        "pop_a": _counts((40, 10), (35, 15), (45, 5), (30, 20), (38, 12)),
        "pop_b": _counts((10, 40), (15, 35), (5, 45), (20, 30), (12, 38)),
        "pop_c": _counts((25, 25), (20, 30), (30, 20), (22, 28), (27, 23)),
    }
    result = await build_population_tree.handler({"populations": populations, "migration_edges": 0})
    text = await text_of(result)
    assert "TreeMix" in text
    assert "pop_a" in text


async def test_too_few_populations_reports_error():
    populations = {"a": _counts((1, 2)), "b": _counts((2, 1))}
    result = await build_population_tree.handler({"populations": populations, "migration_edges": 0})
    text = await text_of(result)
    assert "at least 3" in text


async def test_mismatched_snp_counts_reports_error():
    populations = {"a": _counts((1, 2), (3, 4)), "b": _counts((2, 1)), "c": _counts((1, 1), (2, 2))}
    result = await build_population_tree.handler({"populations": populations, "migration_edges": 0})
    text = await text_of(result)
    assert "same number of SNPs" in text


async def test_malformed_pair_reports_error():
    populations = {"a": [[1, 2, 3]], "b": [[1, 2]], "c": [[1, 2]]}
    result = await build_population_tree.handler({"populations": populations, "migration_edges": 0})
    text = await text_of(result)
    assert "malformed" in text
