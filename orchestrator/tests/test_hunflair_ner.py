"""Real tests for app/tools/hunflair_ner.py -- no mocking, runs the real
HunFlair2 model (loads/downloads on first call, cached after)."""
from app.tools.hunflair_ner import extract_biomedical_entities

SENTENCE = "EGFR mutations are common in non-small cell lung cancer, and Erlotinib is used to treat it."


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_extracts_real_entities():
    result = await extract_biomedical_entities.handler({"text": SENTENCE})
    text = await text_of(result)
    assert "HunFlair2" in text
    assert "EGFR" in text
    assert "Gene" in text
    assert "non-small cell lung cancer" in text
    assert "Disease" in text
    assert "Erlotinib" in text
    assert "Chemical" in text


async def test_empty_text_reports_error():
    result = await extract_biomedical_entities.handler({"text": ""})
    text = await text_of(result)
    assert "must not be empty" in text


async def test_text_too_long_reports_error():
    result = await extract_biomedical_entities.handler({"text": "a" * 5001})
    text = await text_of(result)
    assert "at most 5000" in text


async def test_no_entities_reports_no_matches():
    result = await extract_biomedical_entities.handler({"text": "The quick brown fox jumps over the lazy dog."})
    text = await text_of(result)
    assert "found no biomedical entities" in text or "found" in text
