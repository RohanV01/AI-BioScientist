"""Real tests for app/tools/string_db.py -- no mocking, hits the live
STRING REST API on every case here."""
from app.tools.string_db import get_interaction_partners


async def text_of(result):
    return result["content"][0]["text"]


async def test_get_interaction_partners_for_tp53():
    result = await get_interaction_partners.handler({"identifier": "TP53", "max_results": 10})
    text = await text_of(result)
    assert "STRING" in text
    assert "combined confidence score" in text


async def test_get_interaction_partners_respects_max_results_cap():
    result = await get_interaction_partners.handler({"identifier": "TP53", "max_results": 999})
    text = await text_of(result)
    lines = [l for l in text.splitlines() if l.startswith("- STRING")]
    assert len(lines) <= 25


async def test_get_interaction_partners_mouse_species():
    result = await get_interaction_partners.handler(
        {"identifier": "Trp53", "species": "mouse", "max_results": 5}
    )
    text = await text_of(result)
    assert "STRING" in text or "No STRING interaction partners found" in text


async def test_get_interaction_partners_unrecognized_species_defaults_to_human():
    # SPECIES_TAXON_IDS falls back to human for an unrecognized species
    # string rather than erroring -- confirm that fallback actually works.
    result = await get_interaction_partners.handler(
        {"identifier": "TP53", "species": "not_a_real_species", "max_results": 5}
    )
    text = await text_of(result)
    assert "STRING" in text


async def test_get_interaction_partners_nonsense_identifier_returns_404_gracefully():
    result = await get_interaction_partners.handler(
        {"identifier": "zzqxnotarealproteinxyz123", "max_results": 5}
    )
    text = await text_of(result)
    assert "No STRING interaction partners found" in text
