"""Real tests for app/tools/pyteomics_mass.py -- no mocking, Pyteomics'
actual mass-calculation runs on every case here."""
from app.tools.pyteomics_mass import calculate_peptide_mass


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_peptide_mass_matches_known_reference():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "PEPTIDE"})
    text = await text_of(result)
    assert "[pyteomics:mass]" in text
    assert "799.3600 Da" in text
    assert "800.3672" in text  # [M+H]+


async def test_fragment_ion_ladder_present_for_multi_residue_peptide():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "SAMPLER"})
    text = await text_of(result)
    assert "b/y fragment ions" in text
    assert "b1:" in text and "y1:" in text
    assert "b6:" in text and "y6:" in text
    assert "b7:" not in text  # only len-1 fragment positions for a 7-residue peptide


async def test_lowercase_sequence_is_normalized():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "peptide"})
    text = await text_of(result)
    assert "Peptide PEPTIDE" in text
    assert "799.3600 Da" in text


async def test_empty_sequence_rejected():
    result = await calculate_peptide_mass.handler({"peptide_sequence": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_whitespace_only_sequence_rejected():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "   "})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_non_standard_amino_acid_codes_rejected():
    # B, J, O, U, X, Z are not among the 20 standard one-letter codes
    result = await calculate_peptide_mass.handler({"peptide_sequence": "PEPTIDEX"})
    text = await text_of(result)
    assert "20 standard amino acid" in text


async def test_sequence_over_100_residues_rejected():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "A" * 101})
    text = await text_of(result)
    assert "100 residues or fewer" in text


async def test_sequence_of_exactly_100_residues_accepted():
    result = await calculate_peptide_mass.handler({"peptide_sequence": "A" * 100})
    text = await text_of(result)
    assert "[pyteomics:mass]" in text
    assert "100 residues" in text


async def test_single_residue_peptide_has_no_fragment_ladder():
    # len(seq) == 1 means the b/y ion loop (range(1, 1)) never runs --
    # exercises the boundary condition explicitly.
    result = await calculate_peptide_mass.handler({"peptide_sequence": "P"})
    text = await text_of(result)
    assert "115.0633 Da" in text
    assert "fragment ions" not in text
