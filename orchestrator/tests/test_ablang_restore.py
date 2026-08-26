"""Real tests for app/tools/ablang_restore.py -- no mocking, runs the
real AbLang model (loads/downloads on first call, cached after)."""
from app.tools.ablang_restore import restore_antibody_sequence

HEAVY_SEQ = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAKDRGYSSSWYPMDYWGQGTLVTVSS"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_restores_masked_residues():
    masked = HEAVY_SEQ[:20] + "*" * 10 + HEAVY_SEQ[30:]
    result = await restore_antibody_sequence.handler({"sequence": masked, "chain": "heavy"})
    text = await text_of(result)
    assert "AbLang" in text
    assert "restored 10 masked position" in text
    assert HEAVY_SEQ in text


async def test_invalid_chain_reports_error():
    result = await restore_antibody_sequence.handler({"sequence": "EVQL*ESGG", "chain": "invalid"})
    text = await text_of(result)
    assert "must be 'heavy' or 'light'" in text


async def test_too_short_sequence_reports_error():
    result = await restore_antibody_sequence.handler({"sequence": "EV*L", "chain": "heavy"})
    text = await text_of(result)
    assert "at least 10 residues" in text


async def test_no_mask_reports_error():
    result = await restore_antibody_sequence.handler({"sequence": HEAVY_SEQ, "chain": "heavy"})
    text = await text_of(result)
    assert "must contain at least one" in text


async def test_invalid_characters_report_error():
    result = await restore_antibody_sequence.handler({"sequence": "EVQLZZZ*ESGGXX123", "chain": "heavy"})
    text = await text_of(result)
    assert "standard amino acid letters" in text
