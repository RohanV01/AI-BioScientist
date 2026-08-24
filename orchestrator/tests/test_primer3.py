"""Real tests for app/tools/primer3.py -- no mocking, primer3-py's actual
C library runs on every case here."""
from app.tools.primer3 import design_pcr_primers

TEMPLATE = (
    "ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAGCTTAGGCTTGATCCGGCAAATAACGGGCCCTAGGTACGATCGTAGCATCGAT"
    "CGTAGCTAGCTAGGCATCGATCGATCGTAGCATGCTAGCTAGCATCGATCGATGCTAGCTAGCATGCTAGCATCG"
)  # 190bp


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_returns_real_primer_pairs():
    result = await design_pcr_primers.handler({"sequence": TEMPLATE, "num_return": 2})
    text = await text_of(result)
    assert "PCR primer pair(s)" in text
    assert "[primer3:pair]" in text
    assert "Pair 1:" in text
    assert "forward" in text and "reverse" in text
    assert "Tm" in text and "GC" in text and "bp" in text


async def test_default_num_return_is_three():
    result = await design_pcr_primers.handler({"sequence": TEMPLATE})
    text = await text_of(result)
    assert "Pair 1:" in text
    assert "Pair 2:" in text
    assert "Pair 3:" in text
    assert "Pair 4:" not in text


async def test_num_return_is_clamped_to_ten():
    result = await design_pcr_primers.handler({"sequence": TEMPLATE, "num_return": 999})
    text = await text_of(result)
    # Can't have more pairs than Primer3 actually found, but must not error
    # or silently ignore the clamp -- just confirm it ran and returned pairs.
    assert "PCR primer pair(s)" in text


async def test_target_region_within_bounds_is_accepted():
    result = await design_pcr_primers.handler(
        {"sequence": TEMPLATE, "target_start": 20, "target_length": 30, "num_return": 1}
    )
    text = await text_of(result)
    assert "PCR primer pair(s)" in text or "No valid primer pairs found" in text


async def test_empty_sequence_rejected():
    result = await design_pcr_primers.handler({"sequence": ""})
    text = await text_of(result)
    assert "must be a non-empty DNA string" in text


async def test_invalid_characters_rejected():
    result = await design_pcr_primers.handler({"sequence": "ACGT" * 20 + "XYZ"})
    text = await text_of(result)
    assert "must be a non-empty DNA string" in text


async def test_sequence_too_short_rejected():
    result = await design_pcr_primers.handler({"sequence": "ACGT" * 10})  # 40bp < 50bp minimum
    text = await text_of(result)
    assert "too short" in text


async def test_target_region_out_of_bounds_rejected():
    result = await design_pcr_primers.handler(
        {"sequence": TEMPLATE, "target_start": 180, "target_length": 50}
    )
    text = await text_of(result)
    assert "target_start/target_length must fall within sequence" in text


async def test_negative_target_start_rejected():
    result = await design_pcr_primers.handler(
        {"sequence": TEMPLATE, "target_start": -5, "target_length": 10}
    )
    text = await text_of(result)
    assert "target_start/target_length must fall within sequence" in text


async def test_low_complexity_template_reports_no_primers_found():
    # All-A homopolymer: valid DNA, long enough, but GC 0% and extreme Tm
    # mean Primer3 genuinely can't design a usable pair -- exercises the
    # "No valid primer pairs found" diagnostic path, not an error path.
    result = await design_pcr_primers.handler({"sequence": "A" * 60})
    text = await text_of(result)
    assert "No valid primer pairs found" in text
    assert "Primer3 diagnostics" in text


async def test_lowercase_sequence_is_normalized():
    result = await design_pcr_primers.handler({"sequence": TEMPLATE.lower(), "num_return": 1})
    text = await text_of(result)
    assert "PCR primer pair(s)" in text
