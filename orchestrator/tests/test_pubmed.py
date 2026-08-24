"""Real tests for app/tools/pubmed.py -- no mocking, hits the real NCBI
E-utilities API. Network flakiness (a dropped connection) is possible and
is not the same thing as a logic bug."""
from app.tools.pubmed import search_articles


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_articles():
    result = await search_articles.handler({"query": "CRISPR Cas9 gene editing", "max_results": 3})
    text = await text_of(result)
    assert "PMID" in text
    assert "articles" in result
    assert len(result["articles"]) > 0
    assert result["articles"][0]["pmid"].isdigit()


async def test_max_results_is_respected():
    result = await search_articles.handler({"query": "cancer", "max_results": 2})
    assert len(result["articles"]) <= 2


async def test_max_results_is_clamped_to_twenty():
    result = await search_articles.handler({"query": "cancer", "max_results": 999})
    assert len(result["articles"]) <= 20


async def test_empty_query_returns_no_results_gracefully():
    result = await search_articles.handler({"query": ""})
    text = await text_of(result)
    assert "No PubMed results" in text


async def test_nonsense_query_returns_no_results_gracefully():
    result = await search_articles.handler({"query": "zzzznonexistentqueryimpossiblestring98765"})
    text = await text_of(result)
    assert "No PubMed results" in text


async def test_zero_max_results_does_not_crash():
    # min(0, 20) == 0 -- NCBI's retmax=0 returns an empty idlist, exercising
    # the same "No PubMed results" path rather than crashing or ignoring
    # the value silently.
    result = await search_articles.handler({"query": "cancer", "max_results": 0})
    text = await text_of(result)
    assert "No PubMed results" in text


async def test_negative_max_results_does_not_crash():
    # Only the upper bound is clamped (min(n, 20)) -- a negative value
    # passes through unclamped to NCBI's retmax param. Confirms this
    # degrades gracefully (no results) rather than raising.
    result = await search_articles.handler({"query": "cancer", "max_results": -5})
    text = await text_of(result)
    assert "No PubMed results" in text
