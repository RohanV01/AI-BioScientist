"""Real tests for app/tools/blast_search.py -- no mocking, runs the
real BLAST+ CLI (blastn/makeblastdb, needs the ncbi-blast+ apt package,
present in the Docker image -- see Dockerfile)."""
from app.tools.blast_search import blast_search

QUERY = "ATGGCGCATTACGATCGATCGATCGATCGATCGATCGGCGCATTACGATCG"
CLOSE_MATCH = "ATGGCGCATTACGATCGATCGATCGATCGATCGATCGGCGCATTACGATCG"
FAR_MATCH = "TTTTAAAACCCCGGGGTTTTAAAACCCCGGGGTTTTAAAACCCCGGGGTTTT"


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_exact_match():
    result = await blast_search.handler(
        {"query_sequence": QUERY, "reference_sequences": {"exact": CLOSE_MATCH, "unrelated": FAR_MATCH}, "sequence_type": "nucl"}
    )
    text = await text_of(result)
    assert "BLAST+" in text
    assert "exact" in text
    assert "100.0" in text or "100.00" in text


async def test_empty_query_reports_error():
    result = await blast_search.handler({"query_sequence": "", "reference_sequences": {"a": "ATGC"}})
    text = await text_of(result)
    assert "must not be empty" in text


async def test_invalid_sequence_type_reports_error():
    result = await blast_search.handler({"query_sequence": QUERY, "reference_sequences": {"a": "ATGC"}, "sequence_type": "rna"})
    text = await text_of(result)
    assert "must be 'nucl' or 'prot'" in text


async def test_empty_references_reports_error():
    result = await blast_search.handler({"query_sequence": QUERY, "reference_sequences": {}})
    text = await text_of(result)
    assert "non-empty dict" in text
