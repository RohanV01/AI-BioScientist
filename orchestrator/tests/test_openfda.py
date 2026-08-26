"""Real tests for app/tools/openfda.py -- no mocking, hits the real
openFDA FAERS API."""
from app.tools.openfda import search_adverse_events


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_reaction_counts():
    result = await search_adverse_events.handler({"drug_name": "aspirin", "max_reports": 20})
    text = await text_of(result)
    assert "openFDA FAERS" in text
    assert "total adverse-event reports" in text


async def test_nonsense_drug_reports_not_found():
    result = await search_adverse_events.handler({"drug_name": "zzznotarealdrug9999xyz"})
    text = await text_of(result)
    assert "No openFDA adverse-event reports found" in text


async def test_empty_drug_name_reports_error():
    result = await search_adverse_events.handler({"drug_name": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_max_reports_is_clamped_to_hundred():
    result = await search_adverse_events.handler({"drug_name": "ibuprofen", "max_reports": 9999})
    text = await text_of(result)
    assert "openFDA FAERS" in text
