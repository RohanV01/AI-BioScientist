"""Real tests for app/tools/dada2_denoise.py -- no mocking, runs the
real Rscript wrapper around dada2 (Bioconductor, see Dockerfile). Not
locally testable in this sandbox (no R interpreter available) --
validation-path tests run directly; the happy-path run is deferred to
the batch Docker build/test pass, same as wgcna_modules."""
from app.experiment_context import current_experiment_dir
from app.tools.dada2_denoise import dada2_denoise_amplicons


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_filename_reports_error():
    result = await dada2_denoise_amplicons.handler({"filename": ""})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_no_experiment_context_reports_error():
    result = await dada2_denoise_amplicons.handler({"filename": "reads.fastq"})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_missing_file_reports_error(tmp_path):
    token = current_experiment_dir.set(tmp_path)
    try:
        result = await dada2_denoise_amplicons.handler({"filename": "reads.fastq"})
        text = await text_of(result)
        assert "No uploaded file named" in text
        assert "list_uploaded_files" in text
    finally:
        current_experiment_dir.reset(token)
