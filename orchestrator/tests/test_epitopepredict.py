"""Real tests for app/tools/epitopepredict.py -- no mocking, runs the real
TEPITOPEpan local computation."""
from app.tools.epitopepredict import predict_mhc_ii_epitopes

P53_FRAGMENT = (
    "MEEPQSDPSVEPPLSQETFSDLWKLLPENNVLSPLPSQAMDDLMLSPDDIEQWFTEDPGPDEAPRMPEAAPPVAPAPAAPTPAAPAPAPSWPLSSSVPSQK"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_scored_peptides():
    result = await predict_mhc_ii_epitopes.handler({"sequence": P53_FRAGMENT, "allele": "HLA-DRB1*0101"})
    text = await text_of(result)
    assert "TEPITOPEpan" in text
    assert "score" in text


async def test_top_n_is_respected():
    result = await predict_mhc_ii_epitopes.handler({"sequence": P53_FRAGMENT, "allele": "HLA-DRB1*0101", "top_n": 3})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- ")]
    assert len(lines) == 3


async def test_too_short_sequence_reports_error():
    result = await predict_mhc_ii_epitopes.handler({"sequence": "MEEP", "allele": "HLA-DRB1*0101"})
    text = await text_of(result)
    assert "at least" in text


async def test_unknown_allele_reports_error():
    result = await predict_mhc_ii_epitopes.handler({"sequence": P53_FRAGMENT, "allele": "NOT-A-REAL-ALLELE"})
    text = await text_of(result)
    assert "Unknown allele" in text
