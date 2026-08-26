"""Real tests for app/tools/fpocket_detection.py -- no mocking, fetches
a real PDB structure and runs the real fpocket binary (compiled at
Docker build time, see Dockerfile)."""
from app.tools.fpocket_detection import detect_binding_pockets


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_detects_real_pockets():
    result = await detect_binding_pockets.handler({"pdb_id": "1HVR"})
    text = await text_of(result)
    assert "Fpocket" in text
    assert "druggability" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await detect_binding_pockets.handler({"pdb_id": "ZZZZ"})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_empty_pdb_id_reports_error():
    result = await detect_binding_pockets.handler({"pdb_id": ""})
    text = await text_of(result)
    assert "must not be empty" in text
