"""Real tests for app/tools/xtb_quantum.py -- no mocking, runs the real
xtb binary (apt package, see Dockerfile) and RDKit embedding. Verified
live against a real local xtb install before this file was written
(confirmed xtb prints "normal termination of xtb" to stderr, not
stdout -- a real, non-obvious behavior this tool's parsing depends on)."""
from app.tools.xtb_quantum import compute_quantum_properties


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_real_quantum_properties():
    result = await compute_quantum_properties.handler({"smiles": "CCO"})
    text = await text_of(result)
    assert "xtb GFN2-xTB" in text
    assert "HOMO-LUMO gap" in text
    assert "Total energy" in text


async def test_empty_smiles_reports_error():
    result = await compute_quantum_properties.handler({"smiles": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_invalid_smiles_reports_error():
    result = await compute_quantum_properties.handler({"smiles": "not a smiles"})
    text = await text_of(result)
    assert "not a valid SMILES" in text


async def test_too_many_heavy_atoms_reports_error():
    long_chain = "C" * 65
    result = await compute_quantum_properties.handler({"smiles": long_chain})
    text = await text_of(result)
    assert "heavy atoms" in text
