"""Real tests for app/tools/selscan_nsl.py -- no mocking, runs the real
selscan binary (prebuilt static release, see Dockerfile)."""
import random

from app.tools.selscan_nsl import scan_selection_nsl


async def text_of(result):
    return result["content"][0]["text"]


def _random_haps(n_snps: int, seed: int) -> tuple[str, str]:
    rng = random.Random(seed)
    return (
        "".join(rng.choice("01") for _ in range(n_snps)),
        "".join(rng.choice("01") for _ in range(n_snps)),
    )


async def test_happy_path_computes_real_nsl_scores():
    samples = {}
    for i in range(6):
        hap1, hap2 = _random_haps(20, seed=i)
        samples[f"s{i}"] = {"hap1": hap1, "hap2": hap2}
    result = await scan_selection_nsl.handler({"samples": samples})
    text = await text_of(result)
    assert "selscan" in text


async def test_too_few_samples_reports_error():
    samples = {"s1": {"hap1": "0101010101", "hap2": "0101010101"}, "s2": {"hap1": "0101010101", "hap2": "0101010101"}}
    result = await scan_selection_nsl.handler({"samples": samples})
    text = await text_of(result)
    assert "at least 4" in text


async def test_too_few_snps_reports_error():
    samples = {f"s{i}": {"hap1": "0101", "hap2": "1010"} for i in range(4)}
    result = await scan_selection_nsl.handler({"samples": samples})
    text = await text_of(result)
    assert "at least 10 SNPs" in text


async def test_invalid_allele_reports_error():
    samples = {f"s{i}": {"hap1": "0101210101", "hap2": "0101010101"} for i in range(4)}
    result = await scan_selection_nsl.handler({"samples": samples})
    text = await text_of(result)
    assert "'0'/'1'" in text
