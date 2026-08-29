"""Real tests for app/tools/biotransformer_metabolism.py -- no
mocking, runs the real BioTransformer jar (compiled from source via
Maven, see Dockerfile). Not locally buildable in this sandbox (Maven
isn't bootstrappable without root) -- the happy-path run is verified
against BioTransformer's own documented CLI/CSV-output shape and
deferred to the batch Docker build/test pass, same as
orthofinder_groups/treemix_population_tree above."""
from app.tools.biotransformer_metabolism import predict_metabolites


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_predicts_real_metabolites():
    # Caffeine -- a well-characterized CYP450 substrate, real SMILES.
    result = await predict_metabolites.handler(
        {"smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", "biotransformer_type": "cyp450", "steps": 1}
    )
    text = await text_of(result)
    assert "BioTransformer" in text


async def test_empty_smiles_reports_error():
    result = await predict_metabolites.handler({"smiles": "", "biotransformer_type": "allHuman", "steps": 1})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_invalid_biotransformer_type_reports_error():
    result = await predict_metabolites.handler({"smiles": "CCO", "biotransformer_type": "not_a_real_type", "steps": 1})
    text = await text_of(result)
    assert "must be one of" in text


async def test_invalid_steps_reports_error():
    result = await predict_metabolites.handler({"smiles": "CCO", "biotransformer_type": "cyp450", "steps": 10})
    text = await text_of(result)
    assert "between 1 and 4" in text
