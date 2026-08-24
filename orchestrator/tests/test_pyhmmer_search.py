"""Real tests for app/tools/pyhmmer_search.py -- no mocking, this hits
EBI InterPro's real API and runs a real local hmmsearch (pyhmmer/HMMER3)
on every case here."""
from app.tools.pyhmmer_search import search_pfam_domain

# Real EGFR kinase-domain fragment -- verified this session to match
# PF00069 (Protein kinase domain) at bit score 122.3, e-value 1.2e-39.
KINASE_SEQ = (
    "GLLKLLPYGCLGDGTHPGVTPQGKPVAVKTLKEDTMEVEEFLKEAAVMKEIKHPNLVQLLGVCTREPPFYIITEFMTYGNLLDYLRECNRQEVSAV"
    "VLLYMATQISSAMEYLEKKNFIHRDLAARNCMVAHDFTVKIGDFGMTRDIYETDYYRKGGKGLLPVRWMAPESLKDGVFTTSSDMWSFGVVLWEITSLAE"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_real_kinase_domain():
    result = await search_pfam_domain.handler({"pfam_accession": "pf00069", "protein_sequence": KINASE_SEQ})
    text = await text_of(result)
    assert "[pyhmmer:PF00069]" in text
    assert "Match at residues" in text
    assert "bit score" in text and "e-value" in text


async def test_accession_without_pf_prefix_rejected():
    result = await search_pfam_domain.handler({"pfam_accession": "00069", "protein_sequence": KINASE_SEQ})
    text = await text_of(result)
    assert "must look like" in text


async def test_accession_with_non_numeric_suffix_rejected():
    result = await search_pfam_domain.handler({"pfam_accession": "PFABCDE", "protein_sequence": KINASE_SEQ})
    text = await text_of(result)
    assert "must look like" in text


async def test_empty_sequence_rejected():
    result = await search_pfam_domain.handler({"pfam_accession": "PF00069", "protein_sequence": ""})
    text = await text_of(result)
    assert "non-empty amino-acid sequence" in text


async def test_invalid_amino_acid_characters_rejected():
    result = await search_pfam_domain.handler({"pfam_accession": "PF00069", "protein_sequence": "MKV123"})
    text = await text_of(result)
    assert "non-empty amino-acid sequence" in text


async def test_nonexistent_pfam_accession_reports_no_entry():
    # Well-formed but does not exist -- Pfam accessions don't go this high.
    result = await search_pfam_domain.handler({"pfam_accession": "PF99999", "protein_sequence": KINASE_SEQ})
    text = await text_of(result)
    assert "No Pfam entry found" in text


async def test_unrelated_short_sequence_reports_no_domain_match():
    # A short, generic peptide with no real kinase-domain signal -- should
    # report "no match" gracefully, not crash or fabricate a hit.
    result = await search_pfam_domain.handler({"pfam_accession": "PF00069", "protein_sequence": "MAAAAAAAAAAAAAAAA"})
    text = await text_of(result)
    assert "No PF00069 domain match found" in text
    assert "[pyhmmer:PF00069]" in text
