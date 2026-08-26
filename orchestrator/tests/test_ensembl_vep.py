"""Real tests for app/tools/ensembl_vep.py -- no mocking, hits the real
Ensembl VEP REST API."""
from app.tools.ensembl_vep import predict_variant_effect


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_predicts_real_consequence():
    # A real, well-known BRCA1 missense variant.
    result = await predict_variant_effect.handler({"hgvs_notation": "17:g.43094692G>A"})
    text = await text_of(result)
    assert "most severe consequence" in text
    assert "gene " in text


async def test_malformed_hgvs_reports_error():
    result = await predict_variant_effect.handler({"hgvs_notation": "not a real hgvs string"})
    text = await text_of(result)
    assert "could not parse" in text.lower()


async def test_empty_input_reports_error():
    result = await predict_variant_effect.handler({"hgvs_notation": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
