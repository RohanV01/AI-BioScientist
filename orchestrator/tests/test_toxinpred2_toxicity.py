"""Real tests for app/tools/toxinpred2_toxicity.py -- no mocking, runs
the real toxinpred2 CLI after the Dockerfile's one-line source patch
(see there for the real, confirmed-live bug this fixes). Verified live
locally before this file was written -- patched a real pip install and
got real toxin/non-toxin predictions with real ML scores back."""
from app.tools.toxinpred2_toxicity import predict_peptide_toxicity


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_predicts_real_toxicity():
    sequences = {"test1": "GIGAVLKVLTTGLPALISWIKRKRQQ", "test2": "AAAAAAAAAAAAAAAAAAAA"}
    result = await predict_peptide_toxicity.handler({"sequences": sequences})
    text = await text_of(result)
    assert "ToxinPred2" in text
    assert "test1" in text and "test2" in text


async def test_empty_sequences_reports_error():
    result = await predict_peptide_toxicity.handler({"sequences": {}})
    text = await text_of(result)
    assert "non-empty dict" in text


async def test_invalid_characters_reports_error():
    result = await predict_peptide_toxicity.handler({"sequences": {"seq1": "GIGAVLKVXYZ"}})
    text = await text_of(result)
    assert "standard amino acid letters" in text


async def test_too_many_sequences_reports_error():
    sequences = {f"seq{i}": "GIGAVLKVL" for i in range(51)}
    result = await predict_peptide_toxicity.handler({"sequences": sequences})
    text = await text_of(result)
    assert "at most 50" in text
