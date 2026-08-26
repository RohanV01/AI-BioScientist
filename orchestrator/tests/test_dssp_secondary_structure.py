"""Real tests for app/tools/dssp_secondary_structure.py -- no mocking,
fetches a real PDB structure and runs the real mkdssp CLI (apt dssp
package, present in the Docker image)."""
from app.tools.dssp_secondary_structure import assign_secondary_structure


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_assigns_real_secondary_structure():
    result = await assign_secondary_structure.handler({"pdb_id": "1CRN"})
    text = await text_of(result)
    assert "DSSP" in text
    assert "Summary:" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await assign_secondary_structure.handler({"pdb_id": "ZZZZ"})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_empty_pdb_id_reports_error():
    result = await assign_secondary_structure.handler({"pdb_id": ""})
    text = await text_of(result)
    assert "must not be empty" in text
