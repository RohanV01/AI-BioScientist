"""Real tests for app/tools/sleuth_diffexp.py -- no mocking, runs the
real Rscript wrapper around sleuth (GitHub, see Dockerfile). Not
locally testable in this sandbox (no R interpreter available) --
validation-path tests run directly; the happy-path run is deferred to
the batch Docker build/test pass, same as wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.sleuth_diffexp import sleuth_differential_expression


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_design_filename_reports_error():
    result = await sleuth_differential_expression.handler({"filename": "quants.tar.gz", "design_filename": ""})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_design_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "quants.tar.gz").write_bytes(b"fake")
        result = await sleuth_differential_expression.handler(
            {"filename": "quants.tar.gz", "design_filename": "design.tsv"}
        )
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "design.tsv" in text
    finally:
        current_experiment_dir.reset(token)
