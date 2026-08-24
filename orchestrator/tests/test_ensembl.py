"""Real tests for app/tools/ensembl.py -- no mocking, hits the real
Ensembl REST API."""
from app.tools.ensembl import search_gene


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_resolves_real_gene():
    result = await search_gene.handler({"symbol": "EGFR"})
    text = await text_of(result)
    assert "Ensembl Gene ID ENSG" in text
    assert "EGFR" in text


async def test_default_species_is_human():
    result = await search_gene.handler({"symbol": "TP53"})
    text = await text_of(result)
    assert "ENSG" in text


async def test_explicit_species_is_respected():
    result = await search_gene.handler({"symbol": "Egfr", "species": "mus_musculus"})
    text = await text_of(result)
    assert "Ensembl Gene ID ENSMUSG" in text


async def test_nonexistent_symbol_reports_no_gene_found():
    result = await search_gene.handler({"symbol": "ZZZNOTAREALGENE123"})
    text = await text_of(result)
    assert "No Ensembl gene found" in text


async def test_symbol_with_slash_does_not_crash():
    # symbol is interpolated directly into the URL path
    # (f"{ENSEMBL_URL}/xrefs/symbol/{species}/{symbol}") with no
    # URL-encoding -- a slash in the input could corrupt the path.
    # httpx URL-encodes path segments passed this way, but confirm the
    # tool degrades to "no gene found" rather than raising or hitting
    # the wrong endpoint.
    result = await search_gene.handler({"symbol": "EGFR/BRCA1"})
    text = await text_of(result)
    assert "No Ensembl gene found" in text or "Ensembl Gene ID" in text
