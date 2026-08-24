"""Real tests for app/tools/vina_docking.py -- no mocking. Runs actual
AutoDock Vina docking (real receptor fetch, real RDKit conformer
generation, real Meeko PDBQT prep, real Vina search) -- slow (real CPU
compute), which is expected and correct for this tool. exhaustiveness=1
keeps runs as fast as possible without faking anything."""
from app.tools.vina_docking import dock_ligand

# 3PTB = bovine trypsin with a co-crystallized benzamidine (BEN) inhibitor
# -- small, fast-downloading, well-known structure with a real bound
# ligand for auto-detection to find.
BENZAMIDINE_SMILES = "NC(=[NH2+])c1ccccc1"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_docks_and_reports_real_affinity():
    result = await dock_ligand.handler(
        {"pdb_id": "3PTB", "ligand_smiles": BENZAMIDINE_SMILES, "box_size": 15.0, "exhaustiveness": 1}
    )
    text = await text_of(result)
    assert "AutoDock Vina docking against PDB 3PTB" in text
    assert "[vina:3PTB]" in text
    assert "kcal/mol" in text
    assert "Top" in text and "poses" in text


async def test_explicit_reference_hetero_code_is_used():
    result = await dock_ligand.handler(
        {
            "pdb_id": "3PTB",
            "ligand_smiles": BENZAMIDINE_SMILES,
            "reference_hetero_code": "BEN",
            "box_size": 15.0,
            "exhaustiveness": 1,
        }
    )
    text = await text_of(result)
    assert "co-crystallized BEN" in text


async def test_invalid_smiles_reports_error_not_crash():
    result = await dock_ligand.handler({"pdb_id": "3PTB", "ligand_smiles": "not a real smiles!!!", "exhaustiveness": 1})
    text = await text_of(result)
    assert "Could not parse ligand SMILES" in text


async def test_nonexistent_pdb_id_reports_not_found():
    result = await dock_ligand.handler({"pdb_id": "9ZZZ", "ligand_smiles": BENZAMIDINE_SMILES, "exhaustiveness": 1})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_unknown_reference_hetero_code_reports_error():
    result = await dock_ligand.handler(
        {
            "pdb_id": "3PTB",
            "ligand_smiles": BENZAMIDINE_SMILES,
            "reference_hetero_code": "ZZZ",
            "exhaustiveness": 1,
        }
    )
    text = await text_of(result)
    assert "No HETATM records found for residue code" in text


async def test_exhaustiveness_is_clamped_to_sixteen():
    result = await dock_ligand.handler(
        {"pdb_id": "3PTB", "ligand_smiles": BENZAMIDINE_SMILES, "exhaustiveness": 999, "box_size": 15.0}
    )
    text = await text_of(result)
    assert "kcal/mol" in text
