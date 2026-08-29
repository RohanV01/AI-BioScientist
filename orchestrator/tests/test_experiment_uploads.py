"""Real tests for app/tools/experiment_uploads.py's list_uploaded_files
-- pure local file listing/classification, no subprocess involved so
fully testable here."""
from app.experiment_context import current_experiment_dir
from app.tools.experiment_uploads import list_uploaded_files


async def text_of(result):
    return result["content"][0]["text"]


async def test_no_experiment_context_reports_none_uploaded():
    result = await list_uploaded_files.handler({})
    text = await text_of(result)
    assert "No files have been uploaded" in text


async def test_no_uploads_dir_reports_none_uploaded(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await list_uploaded_files.handler({})
        text = await text_of(result)
        assert "No files have been uploaded" in text
    finally:
        current_experiment_dir.reset(token)


async def test_lists_real_uploaded_files_with_detected_format(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        updir = tmp_path / "uploads"
        updir.mkdir()
        (updir / "reads.fastq").write_text("@r1\nACGT\n+\nIIII\n")
        (updir / "matrix.h5").write_bytes(b"\x89HDF\r\n\x1a\n")

        result = await list_uploaded_files.handler({})
        text = await text_of(result)

        assert "reads.fastq" in text
        assert "format=`fastq`" in text
        assert "dada2_denoise_amplicons" in text
        assert "matrix.h5" in text
        assert "format=`10x_h5_matrix`" in text
        assert "[experiment_uploads:file]" in text
    finally:
        current_experiment_dir.reset(token)
