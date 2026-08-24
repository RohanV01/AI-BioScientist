"""Real tests for app/tools/gnomad.py -- no mocking, hits the real gnomAD
GraphQL API."""
from app.tools.gnomad import get_variant_frequency


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_frequency():
    # A real, well-documented BRCA1 variant.
    result = await get_variant_frequency.handler({"variant_id": "17-43045607-A-T"})
    text = await text_of(result)
    assert "gnomAD variant 17-43045607-A-T" in text
    assert "allele frequency" in text


async def test_malformed_variant_id_does_not_crash():
    # Bug found+fixed: gnomAD's GraphQL API returns an "Invalid variant
    # ID" error (not "not found") for a garbage/malformed ID, which the
    # tool previously only special-cased for "not found" and let anything
    # else fall through to an unhandled RuntimeError. Now both are
    # reported the same graceful way.
    result = await get_variant_frequency.handler({"variant_id": "not-a-real-variant-id"})
    text = await text_of(result)
    assert "No gnomAD record found" in text


async def test_rsid_instead_of_chrom_pos_ref_alt_does_not_crash():
    # The tool explicitly documents it wants chrom-pos-ref-alt, not an
    # rsID -- confirm passing an rsID degrades gracefully rather than
    # raising, same fix as above.
    result = await get_variant_frequency.handler({"variant_id": "rs80357382"})
    text = await text_of(result)
    assert "No gnomAD record found" in text


async def test_well_formed_but_nonexistent_variant_reports_not_found():
    result = await get_variant_frequency.handler({"variant_id": "1-1-A-T"})
    text = await text_of(result)
    assert "No gnomAD record found" in text
