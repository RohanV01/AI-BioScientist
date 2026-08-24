"""Real tests for app/tools/virtual_screening.py -- no mocking, real
RCSB fetches and real AutoDock Vina docking runs. Uses PDB 3PTB
(bovine trypsin with co-crystallized benzamidine, BEN) since it's
small and fast to dock against, and low exhaustiveness/n_poses-equivalent
settings to keep wall-clock time reasonable."""
from app.tools.virtual_screening import batch_dock_ligands, MAX_LIGANDS_PER_SCREEN

BENZAMIDINE = "NC(=N)c1ccccc1"
BENZENE = "c1ccccc1"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_ranks_two_ligands():
    result = await batch_dock_ligands.handler(
        {
            "pdb_id": "3ptb",
            "ligand_smiles_list": [BENZAMIDINE, BENZENE],
            "exhaustiveness": 2,
        }
    )
    text = await text_of(result)
    assert "Virtual screen against PDB 3PTB" in text
    assert "[vina:3PTB]" in text
    assert "kcal/mol" in text
    assert "1." in text and "2." in text


async def test_empty_ligand_list_rejected():
    result = await batch_dock_ligands.handler({"pdb_id": "3PTB", "ligand_smiles_list": []})
    text = await text_of(result)
    assert "must contain at least one SMILES string" in text


async def test_too_many_ligands_rejected():
    ligands = [BENZENE] * (MAX_LIGANDS_PER_SCREEN + 1)
    result = await batch_dock_ligands.handler({"pdb_id": "3PTB", "ligand_smiles_list": ligands})
    text = await text_of(result)
    assert "Too many ligands" in text
    assert str(MAX_LIGANDS_PER_SCREEN) in text


async def test_nonexistent_pdb_id_reports_not_found():
    result = await batch_dock_ligands.handler({"pdb_id": "9ZZZ", "ligand_smiles_list": [BENZENE]})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_invalid_smiles_in_batch_reported_as_failed_not_crashed():
    result = await batch_dock_ligands.handler(
        {
            "pdb_id": "3PTB",
            "ligand_smiles_list": [BENZAMIDINE, "not_a_real_smiles"],
            "exhaustiveness": 2,
        }
    )
    text = await text_of(result)
    assert "not_a_real_smiles: FAILED" in text
    # the valid ligand still gets docked and ranked
    assert "kcal/mol" in text
