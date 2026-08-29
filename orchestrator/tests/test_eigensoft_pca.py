"""Real tests for app/tools/eigensoft_pca.py -- no mocking, runs the
real smartpca binary (apt `eigensoft` package, see Dockerfile)."""
from app.tools.eigensoft_pca import compute_population_pca


async def text_of(result):
    return result["content"][0]["text"]


def _sample(pop, genotypes):
    return {"population": pop, "genotypes": genotypes}


async def test_happy_path_computes_real_pca():
    samples = {
        "s1": _sample("pop_a", [0, 0, 1, 2, 0, 1, 0, 2]),
        "s2": _sample("pop_a", [0, 1, 1, 2, 0, 0, 0, 2]),
        "s3": _sample("pop_b", [2, 2, 0, 0, 2, 1, 2, 0]),
        "s4": _sample("pop_b", [2, 1, 0, 0, 2, 2, 2, 0]),
        "s5": _sample("pop_c", [1, 1, 1, 1, 1, 1, 1, 1]),
        "s6": _sample("pop_c", [1, 2, 1, 0, 1, 1, 1, 1]),
    }
    result = await compute_population_pca.handler({"samples": samples})
    text = await text_of(result)
    assert "smartpca" in text
    assert "s1" in text


async def test_too_few_samples_reports_error():
    result = await compute_population_pca.handler({"samples": {"s1": _sample("a", [0, 1]), "s2": _sample("b", [1, 2])}})
    text = await text_of(result)
    assert "at least 4" in text


async def test_mismatched_lengths_reports_error():
    samples = {
        "s1": _sample("a", [0, 1, 2]),
        "s2": _sample("a", [0, 1]),
        "s3": _sample("b", [2, 1, 0]),
        "s4": _sample("b", [2, 1, 0]),
    }
    result = await compute_population_pca.handler({"samples": samples})
    text = await text_of(result)
    assert "same number of SNPs" in text


async def test_invalid_genotype_code_reports_error():
    samples = {
        "s1": _sample("a", [0, 1, 5]),
        "s2": _sample("a", [0, 1, 2]),
        "s3": _sample("b", [2, 1, 0]),
        "s4": _sample("b", [2, 1, 0]),
    }
    result = await compute_population_pca.handler({"samples": samples})
    text = await text_of(result)
    assert "0, 1, 2, or 9" in text
