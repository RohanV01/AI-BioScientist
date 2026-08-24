"""Real tests for app/tools/uniprot.py -- no mocking, hits the real
UniProt REST API."""
from app.tools.uniprot import get_sequence, search_protein


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_protein():
    result = await search_protein.handler({"query": "EGFR", "organism": "Homo sapiens", "max_results": 3})
    text = await text_of(result)
    assert "UniProt" in text
    assert "EGFR" in text or "egfr" in text.lower()


async def test_max_results_clamped_to_fifteen():
    result = await search_protein.handler({"query": "kinase", "max_results": 999})
    lines = [l for l in (await text_of(result)).split("\n") if l.startswith("- UniProt")]
    assert len(lines) <= 15


async def test_no_organism_filter_still_works():
    result = await search_protein.handler({"query": "TP53"})
    text = await text_of(result)
    assert "UniProt" in text


async def test_nonsense_query_returns_no_entries_gracefully():
    result = await search_protein.handler({"query": "zzzznonexistentproteinquery98765xyz"})
    text = await text_of(result)
    assert "No UniProt entries found" in text


async def test_organism_filter_narrows_results():
    # A real gene name that exists in many species -- constraining by
    # organism should still return a real human hit, not break the query
    # syntax the tool builds internally (organism_name:"...")
    result = await search_protein.handler({"query": "hemoglobin", "organism": "Homo sapiens", "max_results": 2})
    text = await text_of(result)
    assert "UniProt" in text


async def test_get_sequence_happy_path_returns_real_egfr_sequence():
    # P00533 is human EGFR -- a stable, well-known accession.
    result = await get_sequence.handler({"accession": "P00533"})
    text = await text_of(result)
    assert "P00533" in text
    assert "aa:" in text
    # Real EGFR sequence starts with this signal-peptide prefix.
    assert "MRPSGTAGAALLALLAALCPASRA" in text


async def test_get_sequence_malformed_accession_reports_error_not_crash():
    result = await get_sequence.handler({"accession": "not-a-real-accession-format!!"})
    text = await text_of(result)
    assert "not a valid UniProt accession format" in text


async def test_get_sequence_wellformed_but_nonexistent_accession_reports_error():
    # Q00000 is well-formed (passes UniProt's own format check) but
    # unassigned, so UniProt itself returns 404, not 400.
    result = await get_sequence.handler({"accession": "Q00000"})
    text = await text_of(result)
    assert "No UniProt entry found" in text
