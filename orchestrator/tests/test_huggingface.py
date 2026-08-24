"""Real tests for app/tools/huggingface.py -- no mocking. The live
inference call needs a real Hugging Face API token (BYO-credential,
wired through app/vault.py). No token is configured in this environment
(checked HF_TOKEN), so the happy-path live-inference test is skipped
rather than faked; the validation path (which needs no credential, since
it returns before any network call) is fully covered."""
import os

import pytest

from app.tools.huggingface import _build_predict_masked_residue_tool

WT_SEQUENCE = (
    "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVV"
    "HSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWELVMGDGERTHVELLEQAKQAFAAWLQ"
)


def _tool(api_key="dummy-key-unused-for-validation-path"):
    headers = {"Authorization": f"Bearer {api_key}"}
    return _build_predict_masked_residue_tool(headers)


async def text_of(result):
    return result["content"][0]["text"]


async def test_missing_mask_token_is_rejected_without_any_network_call():
    result = await _tool().handler({"masked_sequence": WT_SEQUENCE})  # no <mask>
    text = await text_of(result)
    assert "must contain exactly one '<mask>' token" in text


async def test_empty_sequence_is_rejected_without_any_network_call():
    result = await _tool().handler({"masked_sequence": ""})
    text = await text_of(result)
    assert "must contain exactly one '<mask>' token" in text


@pytest.mark.skipif(not os.environ.get("HF_TOKEN"), reason="no HF_TOKEN configured in this environment")
async def test_happy_path_returns_real_esm2_predictions():
    masked = WT_SEQUENCE[:10] + "<mask>" + WT_SEQUENCE[11:]
    result = await _tool(os.environ["HF_TOKEN"]).handler({"masked_sequence": masked, "top_k": 3})
    text = await text_of(result)
    assert "ESM2 predictions" in text
    assert "probability" in text


@pytest.mark.skipif(not os.environ.get("HF_TOKEN"), reason="no HF_TOKEN configured in this environment")
async def test_top_k_is_clamped_to_twenty():
    masked = WT_SEQUENCE[:10] + "<mask>" + WT_SEQUENCE[11:]
    result = await _tool(os.environ["HF_TOKEN"]).handler({"masked_sequence": masked, "top_k": 999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- ")]
    assert len(lines) <= 20
