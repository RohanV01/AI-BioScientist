"""Real tests for app/tools/spyrmsd_pose.py -- no mocking, runs the real
spyrmsd symmetry-corrected RMSD computation on real RDKit-generated
conformers."""
from rdkit import Chem
from rdkit.Chem import AllChem

from app.tools.spyrmsd_pose import compute_pose_rmsd


def _sdf(seed: int) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    return Chem.MolToMolBlock(mol)

POSE_A = _sdf(42)
POSE_B = _sdf(1)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_real_rmsd():
    result = await compute_pose_rmsd.handler({"pose_a": POSE_A, "pose_b": POSE_B})
    text = await text_of(result)
    assert "Symmetry-corrected pose RMSD" in text
    assert "[spyrmsd:rmsd]" in text


async def test_identical_pose_scores_near_zero():
    result = await compute_pose_rmsd.handler({"pose_a": POSE_A, "pose_b": POSE_A})
    text = await text_of(result)
    assert "0.0000" in text


async def test_missing_input_reports_error():
    result = await compute_pose_rmsd.handler({"pose_a": POSE_A, "pose_b": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_malformed_sdf_reports_error_not_crash():
    result = await compute_pose_rmsd.handler({"pose_a": "not a real sdf block", "pose_b": POSE_B})
    text = await text_of(result)
    assert "failed" in text.lower()
