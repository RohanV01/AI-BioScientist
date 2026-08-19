"""Real tests for app/tools/soltrannet_solubility.py -- no mocking, the
actual pretrained SolTranNet model runs inference on every case here."""
from app.tools.soltrannet_solubility import predict_aqueous_solubility

ASPIRIN = "CC(=O)OC1=CC=CC=C1C(=O)O"
CAFFEINE = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_single_smiles():
    result = await predict_aqueous_solubility.handler({"smiles": [ASPIRIN]})
    text = await text_of(result)
    assert "log S" in text
    assert "[soltrannet:" in text
    assert ASPIRIN in text


async def test_multiple_smiles_all_reported():
    result = await predict_aqueous_solubility.handler({"smiles": [ASPIRIN, CAFFEINE]})
    text = await text_of(result)
    assert text.count("log S") == 2
    assert ASPIRIN in text and CAFFEINE in text


async def test_empty_list_rejected():
    result = await predict_aqueous_solubility.handler({"smiles": []})
    text = await text_of(result)
    assert "must contain at least one" in text


async def test_whitespace_only_entries_filtered_to_empty_rejected():
    result = await predict_aqueous_solubility.handler({"smiles": ["   ", ""]})
    text = await text_of(result)
    assert "must contain at least one" in text


async def test_invalid_smiles_does_not_crash():
    # SolTranNet itself raises an unhandled AttributeError deep in its
    # DataLoader worker on unparseable SMILES -- the tool must catch this
    # via upfront RDKit validation and report it, not crash.
    result = await predict_aqueous_solubility.handler({"smiles": ["not_a_real_smiles_string"]})
    text = await text_of(result)
    assert "Unparseable" in text or "no valid" in text.lower()


async def test_mix_of_valid_and_invalid_smiles_reports_both():
    result = await predict_aqueous_solubility.handler({"smiles": [ASPIRIN, "not_a_real_smiles_string"]})
    text = await text_of(result)
    assert "log S" in text
    assert ASPIRIN in text
    assert "skipped unparseable" in text.lower()
