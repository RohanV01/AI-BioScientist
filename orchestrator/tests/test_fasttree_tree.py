"""Real tests for app/tools/fasttree_tree.py -- no mocking, runs the
real fasttree binary (apt package, see Dockerfile)."""
from app.tools.fasttree_tree import build_fasttree


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_builds_real_newick_tree():
    sequences = {
        "seq1": "ACGTACGTACGTACGTACGTACGTACGTACGT",
        "seq2": "ACGTACGTACGTACGTACGTACGTACGTACGA",
        "seq3": "ACGTACGTACGTACGTACGTACGTACGTTCGT",
        "seq4": "TCGTACGTACGTACGTACGTACGTACGTACGT",
    }
    result = await build_fasttree.handler({"sequences": sequences, "is_nucleotide": True})
    text = await text_of(result)
    assert "FastTree" in text
    assert text.strip().endswith(";") or ";" in text
    assert "seq1" in text


async def test_too_few_sequences_reports_error():
    result = await build_fasttree.handler({"sequences": {"a": "ACGT", "b": "ACGT"}, "is_nucleotide": True})
    text = await text_of(result)
    assert "at least 3" in text


async def test_mismatched_lengths_reports_error():
    result = await build_fasttree.handler(
        {"sequences": {"a": "ACGT", "b": "ACGTAC", "c": "ACGT"}, "is_nucleotide": True}
    )
    text = await text_of(result)
    assert "same length" in text
