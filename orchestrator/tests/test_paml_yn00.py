"""Real tests for app/tools/paml_yn00.py -- no mocking, runs the real
yn00 binary (apt `paml` package, see Dockerfile)."""
from app.tools.paml_yn00 import estimate_dnds


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_real_dnds():
    # Two short in-frame coding sequences differing by a handful of
    # synonymous/nonsynonymous substitutions -- real codon-aligned
    # input, not a mock.
    seq_a = "ATGGCTGATAAAGCTGCTGGTATTCATGGTGGCAAGACC" * 3
    seq_b = "ATGGCAGATAAGGCAGCAGGTATCCACGGCGGCAAAACT" * 3
    result = await estimate_dnds.handler({"sequences": {"gene_a": seq_a, "gene_b": seq_b}})
    text = await text_of(result)
    assert "PAML yn00" in text
    assert "omega" in text


async def test_too_few_sequences_reports_error():
    result = await estimate_dnds.handler({"sequences": {"a": "ATGGCT" * 5}})
    text = await text_of(result)
    assert "at least 2" in text


async def test_non_codon_length_reports_error():
    result = await estimate_dnds.handler({"sequences": {"a": "ATGGC", "b": "ATGCC"}})
    text = await text_of(result)
    assert "multiple of 3" in text


async def test_non_acgt_reports_error():
    result = await estimate_dnds.handler({"sequences": {"a": "ATGGCT", "b": "ATGNCT"}})
    text = await text_of(result)
    assert "non-ACGT" in text
