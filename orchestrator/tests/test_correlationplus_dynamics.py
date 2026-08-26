"""Real tests for app/tools/correlationplus_dynamics.py -- no mocking,
fetches a real PDB structure and runs the real ANM correlation
computation."""
from app.tools.correlationplus_dynamics import compute_residue_correlations


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_real_correlations():
    result = await compute_residue_correlations.handler({"pdb_id": "1A2K", "chain_id": "A"})
    text = await text_of(result)
    assert "Dynamical cross-correlation" in text
    assert "[correlationplus:anm]" in text
    assert "Most correlated pairs" in text
    assert "Most anti-correlated pairs" in text


async def test_default_chain_is_a():
    result = await compute_residue_correlations.handler({"pdb_id": "1A2K"})
    text = await text_of(result)
    assert "chain A" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await compute_residue_correlations.handler({"pdb_id": "ZZZZ"})
    text = await text_of(result)
    assert "No PDB entry found" in text


async def test_unknown_chain_reports_not_found():
    result = await compute_residue_correlations.handler({"pdb_id": "1A2K", "chain_id": "Z"})
    text = await text_of(result)
    assert "not found" in text


async def test_missing_input_reports_error():
    result = await compute_residue_correlations.handler({})
    text = await text_of(result)
    assert "must be non-empty" in text
