"""Real tests for app/tools/pyir_annotate.py -- no mocking, runs the
real PyIR (crowelab-pyir) Python API against a real igblastn binary
(NCBI's own official release, see Dockerfile -- installed there
specifically because the Debian `igblast` apt package was confirmed
live to be missing the actual igblastn/igblastp executables) and the
germline database materialized by `pyir setup` at build time. Not
locally testable in this sandbox (needs the built database) --
validation-path tests run directly; the happy-path run is deferred to
the batch Docker build/test pass."""
from app.tools.pyir_annotate import assign_vdj_genes


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_sequences_reports_error():
    result = await assign_vdj_genes.handler({"sequences": {}})
    text = await text_of(result)
    assert "non-empty dict" in text


async def test_invalid_characters_reports_error():
    result = await assign_vdj_genes.handler({"sequences": {"seq1": "ACGTXYZ"}})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text


async def test_too_many_sequences_reports_error():
    sequences = {f"seq{i}": "ACGT" * 20 for i in range(51)}
    result = await assign_vdj_genes.handler({"sequences": sequences})
    text = await text_of(result)
    assert "at most 50" in text
