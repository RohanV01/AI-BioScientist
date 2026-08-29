"""Real tests for app/tools/fastani_similarity.py -- no mocking, runs
the real fastANI binary (apt package, see Dockerfile). Verified live
before this file was written (confirmed real ~99% ANI between a random
50kb sequence and a 1%-mutated copy of itself, and that FastANI's
default 3000bp fragment length needs a genome-scale, not short-contig,
input to produce any alignment at all)."""
import random

from app.tools.fastani_similarity import compute_genome_ani


def _random_seq(n: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(n))


def _mutate(seq: str, n_mutations: int, seed: int) -> str:
    rng = random.Random(seed)
    chars = list(seq)
    for i in rng.sample(range(len(chars)), n_mutations):
        chars[i] = rng.choice("ACGT")
    return "".join(chars)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_computes_real_ani():
    seq = _random_seq(50000, 1)
    seq2 = _mutate(seq, 500, 2)
    result = await compute_genome_ani.handler({"query_sequence": seq, "reference_sequence": seq2})
    text = await text_of(result)
    assert "FastANI" in text
    assert "%" in text


async def test_too_short_reports_error():
    result = await compute_genome_ani.handler({"query_sequence": "ACGT" * 100, "reference_sequence": "ACGT" * 6000})
    text = await text_of(result)
    assert "at least 20000bp" in text


async def test_invalid_characters_reports_error():
    result = await compute_genome_ani.handler({"query_sequence": "ACGTX" * 5000, "reference_sequence": "ACGT" * 6000})
    text = await text_of(result)
    assert "only A/C/G/T/N" in text
