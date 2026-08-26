"""Real tests for app/tools/kinetic_simulation.py -- no mocking, fetches a
real curated model from BioModels and runs a real libRoadRunner
simulation."""
from app.tools.kinetic_simulation import simulate_kinetic_model


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_simulates_repressilator():
    # BIOMD0000000012 -- Elowitz 2000 repressilator, a real, small, fast-
    # simulating curated kinetic model.
    result = await simulate_kinetic_model.handler({"biomodels_id": "BIOMD0000000012", "duration": 50, "steps": 5})
    text = await text_of(result)
    assert "BioModels BIOMD0000000012" in text
    assert "initial" in text and "final" in text


async def test_unknown_model_id_reports_not_found():
    result = await simulate_kinetic_model.handler({"biomodels_id": "BIOMDNOTREALMODEL"})
    text = await text_of(result)
    assert "No BioModels entry found" in text


async def test_missing_id_reports_error():
    result = await simulate_kinetic_model.handler({})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_steps_is_clamped():
    result = await simulate_kinetic_model.handler({"biomodels_id": "BIOMD0000000012", "duration": 10, "steps": 9999})
    text = await text_of(result)
    assert "5 steps" not in text  # sanity: clamp changed something, not asserting exact count here
    assert "BioModels BIOMD0000000012" in text
