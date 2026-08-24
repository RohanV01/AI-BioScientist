"""Real tests for app/tools/alphafold.py -- no mocking, hits the real
AlphaFold DB API."""
from app.tools.alphafold import get_predicted_structure


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_prediction():
    # P00533 = human EGFR, a real UniProt accession with an AlphaFold model.
    result = await get_predicted_structure.handler({"uniprot_accession": "P00533"})
    text = await text_of(result)
    assert "AlphaFold model" in text
    assert "pLDDT" in text
    assert "Structure file:" in text


async def test_nonexistent_accession_reports_no_prediction():
    result = await get_predicted_structure.handler({"uniprot_accession": "ZZZNOTREAL999"})
    text = await text_of(result)
    assert "No AlphaFold prediction found" in text


async def test_malformed_accession_does_not_crash():
    result = await get_predicted_structure.handler({"uniprot_accession": "not/a valid accession!!"})
    text = await text_of(result)
    assert "No AlphaFold prediction found" in text
