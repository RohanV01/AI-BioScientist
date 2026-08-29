"""Real tests for app/tools/barrnap_rrna.py -- no mocking, runs the
real barrnap binary (apt package, see Dockerfile). Verified live
before this file was written (confirmed real 16S rRNA detection
against an actual partial 16S sequence, and traced barrnap's full
transitive dependency chain -- nhmmer, bedtools -- by extracting the
real .deb locally)."""
from app.tools.barrnap_rrna import predict_rrna_genes

REAL_PARTIAL_16S = (
    "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGTAACAGGAAGAAGCTTGCTTCTTTGCTGACGAGTGGC"
    "GGACGGGTGAGTAATGTCTGGGAAACTGCCTGATGGAGGGGGATAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGACCAAAGAGGGGGA"
    "CCTTCGGGCCTCTTGCCATCGGATGTGCCCAGATGGGATTAGCTAGTAGGTGGGGTAACGGCTCACCTAGGCGACGATCCCTAGCTGGTCTGAGAGGAT"
    "GACCAGCCACACTGGAACTGAGACACGGTCCAGACTCCTACGGGAGGCAGCAGTGGGGAATATTGCACAATGGGCGCAAGCCTGATGCAGCCATGCCGC"
    "GTGTATGAAGAAGGCCTTCGGGTTGTAAAGTACTTTCAGCGGGGAGGAAGGGAGTAAAGTTAATACCTTTGCTCATTGACGTTACCCGCAGAAGAAGCA"
    "CCGGCTAACTCCGTGCCAGCAGCCGCGGTAATACGGAGGGTGCAAGCGTTAATCGGAATTACTGGGCGTAAAGCGCACGCAGGCGGTTTGTTAAGTCAG"
    "ATGTGAAATCCCCGGGCTCAACCTGGGAACTGCATCTGATACTGGCAAGCTTGAGTCTCGTAGAGGGGGGTAGAATTCCAGGTGTAGCGGTGAAATGCG"
    "TAGAGATCTGGAGGAATACCGGTGGCGAAGGCGGCCCCCTGGACGAAGACTGACGCTCAGGTGCGAAAGCGTGGGGAGCAAACAGG"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_detects_real_16s_rrna():
    result = await predict_rrna_genes.handler({"sequence": REAL_PARTIAL_16S, "kingdom": "bac"})
    text = await text_of(result)
    assert "Barrnap" in text
    assert "16S_rRNA" in text


async def test_too_short_reports_error():
    result = await predict_rrna_genes.handler({"sequence": "ACGT" * 20, "kingdom": "bac"})
    text = await text_of(result)
    assert "at least 200bp" in text


async def test_invalid_kingdom_reports_error():
    result = await predict_rrna_genes.handler({"sequence": REAL_PARTIAL_16S, "kingdom": "martian"})
    text = await text_of(result)
    assert "must be one of" in text
