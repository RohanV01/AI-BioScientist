"""Real tests for app/tools/infercnv_analyze.py -- no mocking, runs
the real Rscript wrapper around InferCNV (Bioconductor, see
Dockerfile). Not locally testable in this sandbox (no R interpreter
available) -- validation-path tests run directly; the happy-path run
is deferred to the batch Docker build/test pass, same as
wgcna_modules/dada2_denoise."""
from app.experiment_context import current_experiment_dir
from app.tools.infercnv_analyze import infercnv_detect_cnv


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_ref_group_reports_error():
    result = await infercnv_detect_cnv.handler(
        {"filename": "matrix.h5", "annotations_filename": "annot.tsv", "ref_group_names": ""}
    )
    text = await text_of(result)
    assert "must all be non-empty" in text


async def test_missing_matrix_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "annot.tsv").write_text("cell1\tnormal\n")
        result = await infercnv_detect_cnv.handler(
            {"filename": "matrix.h5", "annotations_filename": "annot.tsv", "ref_group_names": "normal"}
        )
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "matrix.h5" in text
    finally:
        current_experiment_dir.reset(token)


async def test_missing_annotations_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "matrix.h5").write_bytes(b"\x89HDF\r\n\x1a\n")
        result = await infercnv_detect_cnv.handler(
            {"filename": "matrix.h5", "annotations_filename": "annot.tsv", "ref_group_names": "normal"}
        )
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "annot.tsv" in text
    finally:
        current_experiment_dir.reset(token)
