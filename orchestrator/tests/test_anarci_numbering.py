"""Real tests for app/tools/anarci_numbering.py -- no mocking, runs the
real ANARCI HMM-based numbering (requires the `hmmscan` binary, installed
via apt in Dockerfile; not necessarily present on a bare host venv)."""
from app.tools.anarci_numbering import number_antibody_sequence

# A real anti-lysozyme scFv heavy-chain variable domain (VH), from a
# well-known published antibody sequence.
HEAVY_CHAIN_VH = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFT"
    "ISRDNSKNTLYLQMNSLRAEDTAVYYCAKDRLGDYYFDYWGQGTLVTVSS"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_identifies_heavy_chain():
    result = await number_antibody_sequence.handler({"sequence": HEAVY_CHAIN_VH})
    text = await text_of(result)
    assert "domain(s) found" in text
    assert "chain" in text.lower()


async def test_default_scheme_is_imgt():
    result = await number_antibody_sequence.handler({"sequence": HEAVY_CHAIN_VH})
    text = await text_of(result)
    assert "imgt" in text.lower()


async def test_chothia_scheme_selectable():
    result = await number_antibody_sequence.handler({"sequence": HEAVY_CHAIN_VH, "scheme": "chothia"})
    text = await text_of(result)
    assert "chothia" in text.lower()


async def test_invalid_scheme_reports_error():
    result = await number_antibody_sequence.handler({"sequence": HEAVY_CHAIN_VH, "scheme": "not_a_scheme"})
    text = await text_of(result)
    assert "scheme must be one of" in text


async def test_nonsense_sequence_reports_no_domain_found():
    result = await number_antibody_sequence.handler({"sequence": "AAAAAAAAAAAAAAAAAAAAAA"})
    text = await text_of(result)
    assert "No antibody/TCR variable domain recognized" in text


async def test_empty_sequence_reports_error():
    result = await number_antibody_sequence.handler({"sequence": ""})
    text = await text_of(result)
    assert "must be non-empty" in text
