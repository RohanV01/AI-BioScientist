"""Real tests for app/tools/dailymed.py -- no mocking, hits the live
DailyMed REST API on every case here."""
from app.tools.dailymed import search_drug_labels


async def text_of(result):
    return result["content"][0]["text"]


async def test_search_drug_labels_finds_imatinib():
    result = await search_drug_labels.handler({"drug_name": "imatinib", "max_results": 5})
    text = await text_of(result)
    assert "DailyMed set ID" in text
    assert "dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=" in text


async def test_search_drug_labels_respects_max_results_cap():
    result = await search_drug_labels.handler({"drug_name": "acetaminophen", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.splitlines() if l.startswith("- DailyMed set ID")]
    assert len(lines) <= 15


async def test_search_drug_labels_nonsense_query_returns_no_results_gracefully():
    result = await search_drug_labels.handler({"drug_name": "zzqxnotarealdrugxyz123", "max_results": 5})
    text = await text_of(result)
    assert "No DailyMed labels found" in text
