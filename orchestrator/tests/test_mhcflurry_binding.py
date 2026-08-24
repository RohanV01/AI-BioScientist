"""Real tests for app/tools/mhcflurry_binding.py -- no mocking, MHCflurry's
actual pretrained pan-allele model runs on every case here."""
from app.tools.mhcflurry_binding import predict_mhc_binding

# Real CMV pp65 epitope, verified this session: HLA-A*02:01 predicted IC50
# ~16.6nM (strong binder), matching published affinity data.
CMV_EPITOPE = "NLVPMVATV"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_known_strong_binder():
    result = await predict_mhc_binding.handler({"peptides": [CMV_EPITOPE], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "[mhcflurry:HLA-A*02:01]" in text
    assert "NLVPMVATV" in text
    assert "strong binder" in text
    assert "IC50" in text and "nM" in text


async def test_weak_binder_correctly_classified():
    result = await predict_mhc_binding.handler({"peptides": ["AAAAAAAAA"], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "unlikely binder" in text


async def test_multiple_peptides_in_one_call():
    result = await predict_mhc_binding.handler({"peptides": [CMV_EPITOPE, "AAAAAAAAA"], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "NLVPMVATV" in text
    assert "AAAAAAAAA" in text
    assert text.count("IC50") == 2


async def test_lowercase_allele_is_normalized_not_rejected():
    # Regression test: allele wasn't uppercased before the supported_alleles
    # membership check, so a real, valid allele in a different case (e.g.
    # lowercase) was wrongly reported as unsupported -- inconsistent with
    # peptides, which ARE uppercase-normalized two lines above in the source.
    result = await predict_mhc_binding.handler({"peptides": [CMV_EPITOPE], "allele": "hla-a*02:01"})
    text = await text_of(result)
    assert "not in MHCflurry's supported list" not in text
    assert "[mhcflurry:HLA-A*02:01]" in text


async def test_lowercase_peptide_is_normalized():
    result = await predict_mhc_binding.handler({"peptides": [CMV_EPITOPE.lower()], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "NLVPMVATV" in text
    assert "strong binder" in text


async def test_invalid_allele_rejected_gracefully():
    result = await predict_mhc_binding.handler({"peptides": [CMV_EPITOPE], "allele": "NOTREAL"})
    text = await text_of(result)
    assert "not in MHCflurry's supported list" in text


async def test_blank_peptides_rejected():
    result = await predict_mhc_binding.handler({"peptides": ["", "   "], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "at least one non-empty sequence" in text


async def test_too_short_peptide_rejected():
    result = await predict_mhc_binding.handler({"peptides": ["ABC"], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "must be 8-15 residues" in text


async def test_too_long_peptide_rejected():
    result = await predict_mhc_binding.handler({"peptides": ["A" * 16], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "must be 8-15 residues" in text


async def test_ambiguous_residue_rejected():
    # 'X' (ambiguous/unknown residue) is not a standard amino acid code.
    result = await predict_mhc_binding.handler({"peptides": ["NLVPMVATX"], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "must be 8-15 residues, standard amino acids only" in text


async def test_boundary_length_8_accepted():
    result = await predict_mhc_binding.handler({"peptides": ["A" * 8], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "Invalid peptide" not in text
    assert "IC50" in text


async def test_boundary_length_15_accepted():
    result = await predict_mhc_binding.handler({"peptides": ["A" * 15], "allele": "HLA-A*02:01"})
    text = await text_of(result)
    assert "Invalid peptide" not in text
    assert "IC50" in text
