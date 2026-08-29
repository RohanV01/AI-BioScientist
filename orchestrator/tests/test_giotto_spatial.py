"""Real tests for app/tools/giotto_spatial.py -- no mocking, runs the
real Rscript wrapper around Giotto (CRAN, see Dockerfile). Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass, same as wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.giotto_spatial import giotto_analyze_spatial


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_spatial_locs_filename_reports_error():
    result = await giotto_analyze_spatial.handler({"filename": "matrix.h5", "spatial_locs_filename": ""})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_spatial_locs_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "matrix.h5").write_bytes(b"\x89HDF\r\n\x1a\n")
        result = await giotto_analyze_spatial.handler({"filename": "matrix.h5", "spatial_locs_filename": "locs.tsv"})
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "locs.tsv" in text
    finally:
        current_experiment_dir.reset(token)
