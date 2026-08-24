"""Real tests for app/tools/biopandas_structure.py -- no mocking, fetches
and parses the real PDB structure file from RCSB via BioPandas."""
from app.tools.biopandas_structure import get_structure_composition


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_single_chain_no_ligand():
    # 1UBQ = ubiquitin, single chain, no bound heteroatoms besides water.
    result = await get_structure_composition.handler({"pdb_id": "1UBQ"})
    text = await text_of(result)
    assert "PDB 1UBQ composition" in text
    assert "Chains (1): A" in text
    assert "residues" in text


async def test_multi_ligand_structure_reports_bound_groups():
    # 6LU7 = SARS-CoV-2 main protease with a bound inhibitor -- has real
    # non-water HETATM groups.
    result = await get_structure_composition.handler({"pdb_id": "6LU7"})
    text = await text_of(result)
    assert "PDB 6LU7 composition" in text
    assert "Bound heteroatom groups (excluding water): none" not in text


async def test_lowercase_id_is_normalized():
    result = await get_structure_composition.handler({"pdb_id": "1ubq"})
    text = await text_of(result)
    assert "PDB 1UBQ composition" in text


async def test_id_with_surrounding_whitespace_is_normalized():
    result = await get_structure_composition.handler({"pdb_id": "  1UBQ  "})
    text = await text_of(result)
    assert "PDB 1UBQ composition" in text


async def test_nonexistent_id_reports_failure_gracefully():
    result = await get_structure_composition.handler({"pdb_id": "9ZZZ"})
    text = await text_of(result)
    assert "Could not fetch/parse PDB entry" in text
