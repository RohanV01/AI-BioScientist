"""Real tests for app/tools/clinpgx_annotations.py -- no mocking, hits
the real ClinPGx/PharmGKB REST API."""
from app.tools.clinpgx_annotations import get_gene_drug_annotations


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_annotations():
    result = await get_gene_drug_annotations.handler({"gene_symbol": "CYP2D6", "max_results": 5})
    text = await text_of(result)
    assert "PharmGKB/ClinPGx clinical annotations for CYP2D6" in text
    lines = [l for l in text.split("\n") if l.startswith("- [")]
    assert 1 <= len(lines) <= 5


async def test_unknown_gene_reports_not_found():
    result = await get_gene_drug_annotations.handler({"gene_symbol": "ZZZNOTAREALGENE"})
    text = await text_of(result)
    assert "No PharmGKB/ClinPGx clinical annotations found" in text


async def test_empty_input_reports_error():
    result = await get_gene_drug_annotations.handler({"gene_symbol": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_max_results_is_clamped_to_fifty():
    result = await get_gene_drug_annotations.handler({"gene_symbol": "CYP2D6", "max_results": 9999})
    text = await text_of(result)
    lines = [l for l in text.split("\n") if l.startswith("- [")]
    assert len(lines) <= 50
