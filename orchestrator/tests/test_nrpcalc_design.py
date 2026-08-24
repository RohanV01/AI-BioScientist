"""Real tests for app/tools/nrpcalc_design.py -- no mocking, nrpcalc's
actual Maker Mode combinatorial search runs on every case here. Designs
are non-deterministic (no fixed seed), so assertions check structural
properties (part count, length, no-shared-repeat), not exact sequences."""
import re

from app.tools.nrpcalc_design import design_nonrepetitive_parts


async def text_of(result):
    return result["content"][0]["text"]


def _extract_parts(text: str) -> list[str]:
    return re.findall(r"Part \d+: ([ACGTU]+)", text)


def _kmers(seq: str, k: int) -> set[str]:
    return {seq[i : i + k] for i in range(len(seq) - k + 1)}


async def test_happy_path_produces_nonrepetitive_parts():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "max_shared_repeat": 6, "target_size": 3}
    )
    text = await text_of(result)
    assert "[nrpcalc:design]" in text
    assert "3/3 parts found" in text
    parts = _extract_parts(text)
    assert len(parts) == 3
    assert all(len(p) == 16 for p in parts)

    # Independently verify the tool's own claim rather than trusting it:
    # no pair of parts should share any 7-mer (repeat > max_shared_repeat=6).
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            assert _kmers(parts[i], 7).isdisjoint(_kmers(parts[j], 7)), (
                f"Part {i} and {j} share a 7-mer, violating max_shared_repeat=6"
            )


async def test_lowercase_constraint_is_normalized():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "n" * 16, "max_shared_repeat": 6, "target_size": 2}
    )
    text = await text_of(result)
    assert "[nrpcalc:design]" in text
    assert "NNNNNNNNNNNNNNNN" in text  # echoed constraint should be uppercased


async def test_empty_constraint_rejected():
    result = await design_nonrepetitive_parts.handler({"sequence_constraint": ""})
    text = await text_of(result)
    assert "must be non-empty IUPAC" in text


async def test_invalid_iupac_code_rejected():
    result = await design_nonrepetitive_parts.handler({"sequence_constraint": "NNNNNNNNNNNNNNXN"})
    text = await text_of(result)
    assert "must be non-empty IUPAC" in text


async def test_constraint_too_short_rejected():
    result = await design_nonrepetitive_parts.handler({"sequence_constraint": "NNNNNNN"})  # 7bp < 8 minimum
    text = await text_of(result)
    assert "must be between 8 and 200" in text


async def test_constraint_too_long_rejected():
    result = await design_nonrepetitive_parts.handler({"sequence_constraint": "N" * 201})
    text = await text_of(result)
    assert "must be between 8 and 200" in text


async def test_invalid_part_type_rejected():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "part_type": "PROTEIN"}
    )
    text = await text_of(result)
    assert "part_type must be 'DNA' or 'RNA'" in text


async def test_max_shared_repeat_too_low_rejected():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "max_shared_repeat": 1}
    )
    text = await text_of(result)
    assert "max_shared_repeat must be between" in text


async def test_max_shared_repeat_zero_rejected():
    # Regression test: max_shared_repeat=0 is falsy, so "x or default" would
    # have silently replaced it with the default (6) instead of validating
    # and rejecting it. Bug found and fixed in app/tools/nrpcalc_design.py.
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "max_shared_repeat": 0}
    )
    text = await text_of(result)
    assert "max_shared_repeat must be between" in text


async def test_max_shared_repeat_too_high_rejected():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "max_shared_repeat": 16}  # must be <= len-1 = 15
    )
    text = await text_of(result)
    assert "max_shared_repeat must be between" in text


async def test_target_size_zero_rejected():
    # Regression test: target_size=0 is falsy, so "x or default" would have
    # silently replaced it with the default (3) instead of validating and
    # rejecting it. Bug found and fixed in app/tools/nrpcalc_design.py.
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "target_size": 0}
    )
    text = await text_of(result)
    assert "target_size must be between 1 and 20" in text


async def test_target_size_over_twenty_rejected():
    result = await design_nonrepetitive_parts.handler(
        {"sequence_constraint": "N" * 16, "target_size": 21}
    )
    text = await text_of(result)
    assert "target_size must be between 1 and 20" in text
