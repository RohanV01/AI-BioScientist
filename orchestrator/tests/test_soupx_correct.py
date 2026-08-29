"""Real tests for app/tools/soupx_correct.py -- no mocking, runs the
real Rscript wrapper around SoupX (CRAN, see Dockerfile). Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass, same as wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.soupx_correct import soupx_correct_ambient_rna


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_filenames_report_error():
    result = await soupx_correct_ambient_rna.handler({"raw_filename": "", "filtered_filename": "filtered.zip"})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_missing_raw_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await soupx_correct_ambient_rna.handler({"raw_filename": "raw.zip", "filtered_filename": "filtered.zip"})
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "raw.zip" in text
    finally:
        current_experiment_dir.reset(token)


async def test_wrong_format_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "raw.h5").write_bytes(b"\x89HDF\r\n\x1a\n")
        result = await soupx_correct_ambient_rna.handler({"raw_filename": "raw.h5", "filtered_filename": "filtered.zip"})
        text = await text_of(result)
        assert "not a 10x matrix.mtx" in text
    finally:
        current_experiment_dir.reset(token)
