"""Real tests for app/tools/clustalo_align.py -- no mocking, runs the
real clustalo CLI (apt clustalo package, present in the Docker image)."""
from app.tools.clustalo_align import align_sequences_clustalo

SEQS = {
    "seqA": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR",
    "seqB": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKG",
    "seqC": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKA",
}


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_alignment_and_distmat():
    result = await align_sequences_clustalo.handler({"sequences": SEQS})
    text = await text_of(result)
    assert "Clustal Omega" in text
    assert "seqA" in text and "seqB" in text and "seqC" in text
    assert "distance matrix" in text


async def test_too_few_sequences_reports_error():
    result = await align_sequences_clustalo.handler({"sequences": {"only": "MKTAYIAKQ"}})
    text = await text_of(result)
    assert "at least 2" in text


async def test_empty_sequence_reports_error():
    result = await align_sequences_clustalo.handler({"sequences": {"a": "MKT", "b": ""}})
    text = await text_of(result)
    assert "Empty sequence" in text
