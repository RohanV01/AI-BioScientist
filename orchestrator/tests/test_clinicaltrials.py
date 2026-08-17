"""Real tests for app/tools/clinicaltrials.py -- no mocking, hits the
live ClinicalTrials.gov API v2 on every case here."""
from app.tools.clinicaltrials import search_trials


async def text_of(result):
    return result["content"][0]["text"]


async def test_search_trials_finds_imatinib_trials():
    result = await search_trials.handler({"query": "imatinib", "max_results": 5})
    text = await text_of(result)
    assert "NCT ID NCT" in text


async def test_search_trials_respects_max_results_cap():
    result = await search_trials.handler({"query": "cancer", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.splitlines() if l.startswith("- NCT ID")]
    assert len(lines) <= 20


async def test_search_trials_nonsense_query_returns_no_results_gracefully():
    result = await search_trials.handler({"query": "zzqxnonexistentconditionxyz123", "max_results": 5})
    text = await text_of(result)
    assert "No ClinicalTrials.gov trials found" in text
