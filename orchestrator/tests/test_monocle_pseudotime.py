"""Real tests for app/tools/monocle_pseudotime.py -- no mocking, runs
the real Rscript wrapper around Monocle3 (GitHub, see Dockerfile). Not
locally testable in this sandbox (no R interpreter available) --
validation-path tests run directly; the happy-path run is deferred to
the batch Docker build/test pass, same as wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.monocle_pseudotime import monocle_pseudotime_trajectory


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_root_cell_reports_error():
    result = await monocle_pseudotime_trajectory.handler({"filename": "matrix.h5", "root_cell": ""})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await monocle_pseudotime_trajectory.handler({"filename": "matrix.h5", "root_cell": "AAAC-1"})
        text = await text_of(result)
        assert "No uploaded file named" in text
    finally:
        current_experiment_dir.reset(token)
