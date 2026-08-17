"""Real tests for app/tools/msprime.py -- no mocking, msprime's actual
coalescent simulator runs on every case here."""
from app.tools.msprime import simulate_coalescent_diversity


async def text_of(result):
    return result["content"][0]["text"]


async def test_known_good_simulation_matches_prior_verified_result():
    # This exact simulation was live-verified earlier this session: 77
    # segregating sites over a 50,000bp region, reproducible via random_seed.
    result = await simulate_coalescent_diversity.handler(
        {
            "sample_size": 20, "sequence_length": 50000, "population_size": 10000,
            "mutation_rate": 1e-8, "recombination_rate": 1e-8, "random_seed": 42,
        }
    )
    text = await text_of(result)
    assert "[msprime:simulation]" in text
    assert "Segregating sites: 77" in text
    assert "Nucleotide diversity (pi): 0.000428" in text
    assert "Trees in ancestral recombination graph: 77" in text


async def test_defaults_used_when_no_args_given():
    result = await simulate_coalescent_diversity.handler({})
    text = await text_of(result)
    assert "n=20 haploid samples" in text
    assert "L=10000bp" in text
    assert "Ne=10000" in text


async def test_explicit_zero_mutation_rate_is_actually_used_not_replaced_by_default():
    # Regression test: `float(args.get("mutation_rate") or 1e-8)` used to
    # treat an explicit 0.0 as falsy and silently substitute the 1e-8
    # default instead. mu=0.0 is a legitimate request (pure genealogy, no
    # new mutations) and must produce zero diversity/segregating sites.
    result = await simulate_coalescent_diversity.handler(
        {"sample_size": 10, "sequence_length": 1000, "mutation_rate": 0.0, "random_seed": 1}
    )
    text = await text_of(result)
    assert "mu=0.0" in text
    assert "Segregating sites: 0" in text
    assert "Nucleotide diversity (pi): 0.000000" in text
    # Tajima's D is mathematically undefined with zero segregating sites --
    # must be reported plainly, not a bare "nan".
    assert "Tajima's D: undefined (no segregating sites)" in text
    assert "nan" not in text.lower().replace("undefined", "")


async def test_explicit_zero_population_size_is_rejected_not_replaced_by_default():
    # Same falsy-default bug class: population_size=0 used to silently
    # become 10_000 instead of triggering this validation message.
    result = await simulate_coalescent_diversity.handler(
        {"sample_size": 10, "sequence_length": 1000, "population_size": 0}
    )
    text = await text_of(result)
    assert "population_size must be a positive integer" in text


async def test_same_seed_is_reproducible():
    args = {"sample_size": 8, "sequence_length": 2000, "mutation_rate": 1e-7, "random_seed": 7}
    result1 = await simulate_coalescent_diversity.handler(args)
    result2 = await simulate_coalescent_diversity.handler(args)
    assert await text_of(result1) == await text_of(result2)


async def test_sample_size_too_small_rejected():
    result = await simulate_coalescent_diversity.handler({"sample_size": 1})
    text = await text_of(result)
    assert "sample_size must be between 2 and 1000" in text


async def test_sample_size_too_large_rejected():
    result = await simulate_coalescent_diversity.handler({"sample_size": 1001})
    text = await text_of(result)
    assert "sample_size must be between 2 and 1000" in text


async def test_sequence_length_too_short_rejected():
    result = await simulate_coalescent_diversity.handler({"sequence_length": 50})
    text = await text_of(result)
    assert "sequence_length must be between 100bp" in text


async def test_sequence_length_too_long_rejected():
    result = await simulate_coalescent_diversity.handler({"sequence_length": 20_000_000})
    text = await text_of(result)
    assert "sequence_length must be between 100bp" in text


async def test_negative_population_size_rejected():
    result = await simulate_coalescent_diversity.handler({"population_size": -5})
    text = await text_of(result)
    assert "population_size must be a positive integer" in text
