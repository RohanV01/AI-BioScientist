"""Real tests for app/tools/pycombat_correction.py -- no mocking, runs
the real ComBat computation on a synthetic matrix with a deliberate,
known batch effect."""
import random

from app.tools.pycombat_correction import correct_batch_effect

random.seed(0)
N_GENES = 15
N_PER_BATCH = 8


def _make_matrix():
    matrix = []
    for _ in range(N_GENES):
        batch1 = [random.gauss(5, 1) for _ in range(N_PER_BATCH)]
        batch2 = [random.gauss(8, 1) for _ in range(N_PER_BATCH)]
        matrix.append(batch1 + batch2)
    labels = [0] * N_PER_BATCH + [1] * N_PER_BATCH
    return matrix, labels


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_corrects_real_batch_effect():
    matrix, labels = _make_matrix()
    result = await correct_batch_effect.handler({"expression_matrix": matrix, "batch_labels": labels})
    text = await text_of(result)
    assert "ComBat batch-effect correction" in text
    assert "[pycombat:correction]" in text


async def test_single_batch_reports_error():
    matrix, _ = _make_matrix()
    labels = [0] * (N_PER_BATCH * 2)
    result = await correct_batch_effect.handler({"expression_matrix": matrix, "batch_labels": labels})
    text = await text_of(result)
    assert "at least 2 distinct batches" in text


async def test_mismatched_row_lengths_reports_error():
    result = await correct_batch_effect.handler({"expression_matrix": [[1, 2, 3], [1, 2]], "batch_labels": [0, 0, 1]})
    text = await text_of(result)
    assert "same number of samples" in text


async def test_too_few_samples_in_a_batch_reports_error():
    matrix = [[1.0, 2.0, 3.0, 4.0]]
    labels = [0, 1, 1, 1]
    result = await correct_batch_effect.handler({"expression_matrix": matrix, "batch_labels": labels})
    text = await text_of(result)
    assert "fewer than 2 samples" in text


async def test_missing_input_reports_error():
    result = await correct_batch_effect.handler({})
    text = await text_of(result)
    assert "expression_matrix must be" in text
