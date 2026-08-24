"""Real tests for app/tools/plip_interactions.py -- no mocking, real RCSB
fetches and a real local PLIP analysis run on every case here."""
from app.tools.plip_interactions import profile_ligand_interactions


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_egfr_erlotinib_known_hydrogen_bond():
    # Verified this session: PDB 1M17 (EGFR + erlotinib/AQ4) has a real
    # hinge-binding hydrogen bond to Met769 at 2.70A.
    result = await profile_ligand_interactions.handler({"pdb_id": "1m17"})
    text = await text_of(result)
    assert "[plip:1M17]" in text
    assert "ligand AQ4" in text
    assert "MET769" in text
    assert "2.70A" in text
    assert "Hydrophobic contacts" in text


async def test_pdb_id_is_case_normalized():
    lower = await text_of(await profile_ligand_interactions.handler({"pdb_id": "1m17"}))
    upper = await text_of(await profile_ligand_interactions.handler({"pdb_id": "1M17"}))
    assert lower == upper


async def test_explicit_matching_hetero_code_selects_same_ligand():
    result = await profile_ligand_interactions.handler({"pdb_id": "1M17", "hetero_code": "aq4"})
    text = await text_of(result)
    assert "ligand AQ4" in text
    assert "MET769" in text


async def test_nonexistent_pdb_id_reported_gracefully():
    result = await profile_ligand_interactions.handler({"pdb_id": "ZZZZ"})
    text = await text_of(result)
    assert "No PDB entry found for ZZZZ" in text


async def test_wrong_hetero_code_reports_available_ligands():
    result = await profile_ligand_interactions.handler({"pdb_id": "1M17", "hetero_code": "XXX"})
    text = await text_of(result)
    assert "not found in this structure" in text
    assert "AQ4" in text


async def test_structure_with_no_ligands_reported_gracefully():
    # Crambin (1CRN) is a small, ligand-free protein structure.
    result = await profile_ligand_interactions.handler({"pdb_id": "1CRN"})
    text = await text_of(result)
    assert "No ligands found in this structure" in text
