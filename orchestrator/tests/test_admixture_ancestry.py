"""Real tests for app/tools/admixture_ancestry.py -- no mocking, runs
the real admixture binary (prebuilt static release, see Dockerfile)."""
from app.tools.admixture_ancestry import infer_ancestry


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_infers_real_ancestry():
    samples = {
        "s1": [0, 0, 1, 2, 0, 1, 0, 2, 0, 1],
        "s2": [0, 1, 1, 2, 0, 0, 0, 2, 1, 0],
        "s3": [2, 2, 0, 0, 2, 1, 2, 0, 2, 1],
        "s4": [2, 1, 0, 0, 2, 2, 2, 0, 2, 2],
        "s5": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "s6": [1, 2, 1, 0, 1, 1, 1, 1, 0, 1],
    }
    result = await infer_ancestry.handler({"samples": samples, "k": 2})
    text = await text_of(result)
    assert "ADMIXTURE" in text
    assert "s1" in text


async def test_too_few_samples_reports_error():
    result = await infer_ancestry.handler({"samples": {"s1": [0, 1], "s2": [1, 2]}, "k": 2})
    text = await text_of(result)
    assert "at least 4" in text


async def test_invalid_k_reports_error():
    samples = {f"s{i}": [0, 1, 2] for i in range(5)}
    result = await infer_ancestry.handler({"samples": samples, "k": 1})
    text = await text_of(result)
    assert "between 2 and" in text


async def test_mismatched_lengths_reports_error():
    samples = {"s1": [0, 1, 2], "s2": [0, 1], "s3": [2, 1, 0], "s4": [2, 1, 0]}
    result = await infer_ancestry.handler({"samples": samples, "k": 2})
    text = await text_of(result)
    assert "same number of SNPs" in text
