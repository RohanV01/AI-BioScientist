"""Real tests for app/tools/usalign_tmscore.py -- no mocking, fetches
real PDB structures and runs the real USalign binary (compiled at
Docker build time, see Dockerfile)."""
from app.tools.usalign_tmscore import usalign_tmscore


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_identical_structure_scores_near_one():
    result = await usalign_tmscore.handler({"pdb_id_a": "1CRN", "pdb_id_b": "1CRN"})
    text = await text_of(result)
    assert "US-align" in text
    assert "TM-score" in text


async def test_missing_pdb_id_a_reports_error():
    result = await usalign_tmscore.handler({"pdb_id_a": "", "pdb_id_b": "1CRN"})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await usalign_tmscore.handler({"pdb_id_a": "ZZZZ", "pdb_id_b": "1CRN"})
    text = await text_of(result)
    assert "No PDB entry found" in text
