"""Real tests for app/file_uploads.py -- pure local file classification
and archive extraction, no R/subprocess involved so fully testable
here (unlike the R-bridge tool wrappers that consume its output)."""
import tarfile
import zipfile

from app.file_uploads import classify_upload, extract_bundle


def test_classifies_fastq(tmp_path):
    p = tmp_path / "reads.fastq.gz"
    p.write_bytes(b"@read1\nACGT\n+\nIIII\n")
    assert classify_upload(p) == "fastq"


def test_classifies_h5_matrix(tmp_path):
    p = tmp_path / "filtered_feature_bc_matrix.h5"
    p.write_bytes(b"\x89HDF\r\n\x1a\n")
    assert classify_upload(p) == "10x_h5_matrix"


def test_classifies_table(tmp_path):
    p = tmp_path / "design.tsv"
    p.write_text("sample1\tconditionA\n")
    assert classify_upload(p) == "table"


def test_unknown_extension(tmp_path):
    p = tmp_path / "notes.docx"
    p.write_bytes(b"not real")
    assert classify_upload(p) == "unknown"


def test_classifies_10x_mtx_bundle_zip(tmp_path):
    archive = tmp_path / "matrices.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample/matrix.mtx", "%%MatrixMarket matrix coordinate integer general\n")
        zf.writestr("sample/barcodes.tsv", "AAAC-1\n")
        zf.writestr("sample/features.tsv", "ENSG001\tGENE1\n")
    assert classify_upload(archive) == "10x_mtx_bundle"


def test_classifies_quant_dir_bundle_targz(tmp_path):
    archive = tmp_path / "quants.tar.gz"
    sample_dir = tmp_path / "sample1"
    sample_dir.mkdir()
    quant_file = sample_dir / "quant.sf"
    quant_file.write_text("Name\tLength\tEffectiveLength\tTPM\tNumReads\n")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(sample_dir, arcname="sample1")
    assert classify_upload(archive) == "quant_dir_bundle"


def test_unrecognized_archive_contents(tmp_path):
    archive = tmp_path / "misc.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    assert classify_upload(archive) == "unrecognized_archive"


def test_extract_bundle_unwraps_single_top_level_dir(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("sample/matrix.mtx", "data")
        zf.writestr("sample/barcodes.tsv", "AAAC-1\n")
    result = extract_bundle(archive)
    assert result.name == "sample"
    assert (result / "matrix.mtx").is_file()


def test_extract_bundle_is_idempotent(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("matrix.mtx", "data")
    first = extract_bundle(archive)
    second = extract_bundle(archive)
    assert first == second
