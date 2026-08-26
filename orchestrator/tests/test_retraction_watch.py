"""Real tests for app/tools/retraction_watch.py -- no mocking, hits the
real NCBI E-utilities API against known-retracted and known-clean PMIDs.
"""
from app.tools.retraction_watch import check_retraction_status


async def text_of(result):
    return result["content"][0]["text"]


async def test_known_retracted_pmid_is_flagged():
    # PMID 9500320 -- Wakefield et al., Lancet 1998, retracted 2010.
    result = await check_retraction_status.handler({"pmid": "9500320"})
    text = await text_of(result)
    assert "RETRACTED" in text


async def test_known_clean_pmid_is_not_flagged():
    # PMID 25760099 -- an ordinary, never-retracted PubMed record.
    result = await check_retraction_status.handler({"pmid": "25760099"})
    text = await text_of(result)
    assert "RETRACTED" not in text
    assert "no retraction" in text.lower()


async def test_doi_is_resolved_to_pmid_and_checked():
    # Same Wakefield paper, looked up by DOI instead of PMID.
    result = await check_retraction_status.handler({"doi": "10.1016/S0140-6736(97)11096-0"})
    text = await text_of(result)
    assert "RETRACTED" in text


async def test_unknown_pmid_reports_no_record_found():
    result = await check_retraction_status.handler({"pmid": "999999999999"})
    text = await text_of(result)
    assert "No PubMed record found" in text


async def test_missing_input_reports_error():
    result = await check_retraction_status.handler({})
    text = await text_of(result)
    assert "Provide either pmid or doi" in text
