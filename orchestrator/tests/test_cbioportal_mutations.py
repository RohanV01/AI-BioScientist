"""Real tests for app/tools/cbioportal_mutations.py -- no mocking, hits
the real cBioPortal REST API."""
from app.tools.cbioportal_mutations import get_gene_mutations_in_study


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_mutations():
    result = await get_gene_mutations_in_study.handler(
        {"gene_symbol": "TP53", "study_id": "acc_tcga", "max_results": 5}
    )
    text = await text_of(result)
    assert "cBioPortal mutations: TP53" in text
    lines = [l for l in text.split("\n") if l.startswith("- sample")]
    assert 1 <= len(lines) <= 5


async def test_unknown_gene_reports_not_found():
    result = await get_gene_mutations_in_study.handler({"gene_symbol": "ZZZNOTAREALGENE", "study_id": "acc_tcga"})
    text = await text_of(result)
    assert "No cBioPortal gene record found" in text


async def test_unknown_study_reports_error_not_crash():
    result = await get_gene_mutations_in_study.handler({"gene_symbol": "TP53", "study_id": "zzznotarealstudy999"})
    text = await text_of(result)
    assert "cBioPortal query failed" in text or "No mutations found" in text


async def test_missing_input_reports_error():
    result = await get_gene_mutations_in_study.handler({"gene_symbol": "TP53"})
    text = await text_of(result)
    assert "must be non-empty" in text
