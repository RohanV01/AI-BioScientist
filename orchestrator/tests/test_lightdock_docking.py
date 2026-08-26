"""Real tests for app/tools/lightdock_docking.py -- no mocking, fetches a
real PDB structure and runs the real LightDock 3-stage CLI pipeline."""
from app.tools.lightdock_docking import dock_protein_protein


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_docks_real_chains():
    # 1A2K is a real, small (~124-residue) two-chain complex, a fast
    # real-world case for this test's timeout budget.
    result = await dock_protein_protein.handler({"pdb_id": "1A2K", "receptor_chain": "A", "ligand_chain": "B"})
    text = await text_of(result)
    assert "LightDock protein-protein docking" in text
    assert "[lightdock:1A2K]" in text
    assert "LightDock score" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await dock_protein_protein.handler({"pdb_id": "ZZZZ", "receptor_chain": "A", "ligand_chain": "B"})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_unknown_chain_reports_not_found():
    result = await dock_protein_protein.handler({"pdb_id": "1A2K", "receptor_chain": "A", "ligand_chain": "Z"})
    text = await text_of(result)
    assert "not found in PDB" in text


async def test_same_chain_reports_error():
    result = await dock_protein_protein.handler({"pdb_id": "1A2K", "receptor_chain": "A", "ligand_chain": "A"})
    text = await text_of(result)
    assert "must be different" in text


async def test_missing_input_reports_error():
    result = await dock_protein_protein.handler({"pdb_id": "1A2K"})
    text = await text_of(result)
    assert "must all be non-empty" in text
