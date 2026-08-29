"""Real tests for app/tools/pixy_diversity.py -- no mocking, calls the
real pixy.calc functions (installed from source, see requirements.txt
-- confirmed live before wiring: pip-installed from GitHub, ran
calc_pi/calc_dxy directly against real GenotypeArray data, and verified
this tool's own handler produces the same real numbers)."""
from app.tools.pixy_diversity import compute_nucleotide_diversity


async def text_of(result):
    return result["content"][0]["text"]


def _pop(*rows):
    return {f"s{i}": row for i, row in enumerate(rows)}


async def test_happy_path_computes_real_pi_and_dxy():
    populations = {
        "pop_a": _pop([[0, 0], [0, 1], [1, 1]], [[0, 0], [0, 0], [0, 1]], [[1, 1], [0, 1], [0, 0]]),
        "pop_b": _pop([[1, 1], [1, 1], [0, 1]], [[0, 0], [0, 1], [0, 0]], [[1, 1], [1, 0], [0, 0]]),
    }
    result = await compute_nucleotide_diversity.handler({"populations": populations})
    text = await text_of(result)
    assert "pixy" in text
    assert "pi(pop_a)" in text
    assert "dxy(pop_a, pop_b)" in text


async def test_single_population_computes_only_pi():
    populations = {"pop_a": _pop([[0, 0], [0, 1]], [[1, 1], [0, 0]])}
    result = await compute_nucleotide_diversity.handler({"populations": populations})
    text = await text_of(result)
    assert "pi(pop_a)" in text
    assert "dxy" not in text


async def test_invalid_allele_reports_error():
    populations = {"pop_a": {"s0": [[0, 2]]}}
    result = await compute_nucleotide_diversity.handler({"populations": populations})
    text = await text_of(result)
    assert "invalid genotype call" in text


async def test_mismatched_snp_counts_reports_error():
    populations = {"pop_a": {"s0": [[0, 0], [0, 1]], "s1": [[0, 0]]}}
    result = await compute_nucleotide_diversity.handler({"populations": populations})
    text = await text_of(result)
    assert "same number of SNP genotype calls" in text
