"""Real tests for app/tools/seurat_analyze.py -- no mocking, runs the
real Rscript wrapper around Seurat (CRAN, see Dockerfile). Not locally
testable in this sandbox (no R interpreter available) -- validation-
path tests run directly; the happy-path run is deferred to the batch
Docker build/test pass, same as wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.seurat_analyze import seurat_analyze_scrna


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_filename_reports_error():
    result = await seurat_analyze_scrna.handler({"filename": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_missing_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await seurat_analyze_scrna.handler({"filename": "matrix.h5"})
        text = await text_of(result)
        assert "No uploaded file named" in text
    finally:
        current_experiment_dir.reset(token)


async def test_wrong_format_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "notes.csv").write_text("a,b\n1,2\n")
        result = await seurat_analyze_scrna.handler({"filename": "notes.csv"})
        text = await text_of(result)
        assert "not a 10x-format matrix" in text
    finally:
        current_experiment_dir.reset(token)
