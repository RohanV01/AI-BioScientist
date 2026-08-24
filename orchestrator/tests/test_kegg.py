"""Real tests for app/tools/kegg.py -- no mocking, hits the live KEGG
REST API on every case here."""
from app.tools.kegg import get_gene_pathways


async def text_of(result):
    return result["content"][0]["text"]


async def test_get_gene_pathways_for_tp53():
    result = await get_gene_pathways.handler({"gene_symbol": "TP53"})
    text = await text_of(result)
    assert "KEGG hsa04115: p53 signaling pathway" in text
    assert "KEGG hsa04210: Apoptosis" in text


async def test_get_gene_pathways_nonexistent_gene_returns_404_gracefully():
    result = await get_gene_pathways.handler({"gene_symbol": "ZZQXNOTAREALGENE123"})
    text = await text_of(result)
    assert "No KEGG entry found" in text
