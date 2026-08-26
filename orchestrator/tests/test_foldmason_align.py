"""Real tests for app/tools/foldmason_align.py -- no mocking, fetches
real PDB structures and runs the real foldmason CLI (downloaded as a
static binary, see Dockerfile)."""
from app.tools.foldmason_align import foldmason_align


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_aligns_real_structures():
    result = await foldmason_align.handler({"pdb_ids": ["1CRN", "1UBQ", "1LYZ"]})
    text = await text_of(result)
    assert "FoldMason" in text


async def test_too_few_structures_reports_error():
    result = await foldmason_align.handler({"pdb_ids": ["1CRN", "1UBQ"]})
    text = await text_of(result)
    assert "at least 3" in text


async def test_all_unknown_ids_reports_error():
    result = await foldmason_align.handler({"pdb_ids": ["ZZZZ", "YYYY", "XXXX"]})
    text = await text_of(result)
    assert "Only found 0" in text
