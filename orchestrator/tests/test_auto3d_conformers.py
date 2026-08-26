"""Real tests for app/tools/auto3d_conformers.py -- no mocking, runs the
real Auto3D isomer-enumeration + AIMNET geometry optimization."""
from app.tools.auto3d_conformers import generate_3d_conformer


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_generates_real_conformer():
    result = await generate_3d_conformer.handler({"smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"})
    text = await text_of(result)
    assert "Auto3D 3D conformer" in text
    assert "[auto3d:conformer]" in text
    # A real MDL Molfile block has a "V2000" counts line.
    assert "V2000" in text


async def test_invalid_smiles_reports_error():
    result = await generate_3d_conformer.handler({"smiles": "not a real smiles!!!"})
    text = await text_of(result)
    assert "not a valid SMILES" in text


async def test_empty_input_reports_error():
    result = await generate_3d_conformer.handler({"smiles": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
