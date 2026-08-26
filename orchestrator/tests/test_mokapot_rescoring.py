"""Real tests for app/tools/mokapot_rescoring.py -- no mocking, runs the
real mokapot semi-supervised rescoring on a synthetic-but-realistically-
sized PSM set (targets score higher than decoys, on average, same as a
real search engine's output would)."""
import random

from app.tools.mokapot_rescoring import rescore_psms

random.seed(0)


def _make_psms(n: int = 2000) -> list[dict]:
    psms = []
    for i in range(n):
        is_target = random.random() > 0.5
        score = random.gauss(8, 1.5) if is_target else random.gauss(2, 1.5)
        psms.append(
            {
                "spectrum_id": f"spec{i}",
                "peptide": f"PEPTIDE{i}",
                "is_target": is_target,
                "xcorr": score,
                "mass_error": random.gauss(0, 1),
            }
        )
    return psms


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_scored_psms():
    result = await rescore_psms.handler({"psms": _make_psms(), "target_fdr": 0.05})
    text = await text_of(result)
    assert "mokapot PSM rescoring" in text
    assert "q-value" in text


async def test_too_few_psms_reports_error():
    result = await rescore_psms.handler({"psms": _make_psms(5)})
    text = await text_of(result)
    assert "at least 20" in text


async def test_missing_field_reports_error():
    bad = [{"spectrum_id": "s1", "peptide": "PEP1", "xcorr": 5.0}] * 25
    result = await rescore_psms.handler({"psms": bad})
    text = await text_of(result)
    assert "missing required field" in text


async def test_no_feature_columns_reports_error():
    bad = [{"spectrum_id": f"s{i}", "peptide": f"PEP{i}", "is_target": True} for i in range(25)]
    result = await rescore_psms.handler({"psms": bad})
    text = await text_of(result)
    assert "at least one numeric search-engine score" in text
