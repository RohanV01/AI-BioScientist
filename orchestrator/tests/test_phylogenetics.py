"""Real tests for app/tools/phylogenetics.py's three tools -- no mocking,
real IQ-TREE (piqtree), dendropy, and PhyKIT CLI runs on every case here."""
from app.tools.phylogenetics import analyze_tree, build_phylogenetic_tree, compute_tree_statistics

# 4 real-shape aligned DNA sequences (same length, some divergence) -- enough
# for a real ML tree search, not biologically meaningful taxa but exercises
# the actual IQ-TREE inference path with real sequence data.
ALIGNED_SEQS = {
    "SpeciesA": "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT",
    "SpeciesB": "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGA",
    "SpeciesC": "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTTTTTACGTACGTACGTACGT",
    "SpeciesD": "TTTTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT",
}
SIMPLE_TREE = "(A:0.1,B:0.1,(C:0.1,D:0.1):0.1);"


async def text_of(result):
    return result["content"][0]["text"]


# -- build_phylogenetic_tree --


async def test_build_tree_happy_path_real_ml_inference():
    result = await build_phylogenetic_tree.handler({"sequences": ALIGNED_SEQS})
    text = await text_of(result)
    assert "[piqtree:tree]" in text
    assert "Maximum-likelihood tree for 4 taxa" in text
    for name in ALIGNED_SEQS:
        assert name in text
    assert text.rstrip().endswith(";")


async def test_build_tree_too_few_sequences_rejected():
    result = await build_phylogenetic_tree.handler({"sequences": {"A": "ACGT", "B": "ACGT"}})
    text = await text_of(result)
    assert "at least 3" in text


async def test_build_tree_non_dict_input_rejected():
    result = await build_phylogenetic_tree.handler({"sequences": ["A", "B", "C"]})
    text = await text_of(result)
    assert "must be a dict" in text


async def test_build_tree_mismatched_lengths_rejected():
    result = await build_phylogenetic_tree.handler({"sequences": {"A": "ACGT", "B": "ACGTA", "C": "ACGT"}})
    text = await text_of(result)
    assert "same length" in text
    assert "[4, 5]" in text


# -- analyze_tree --


async def test_analyze_tree_happy_path_with_real_patristic_distance():
    newick = SIMPLE_TREE
    result = await analyze_tree.handler({"newick": newick, "taxon_a": "A", "taxon_b": "C"})
    text = await text_of(result)
    assert "[dendropy:tree]" in text
    assert "4 taxa" in text
    assert "Patristic distance A <-> C:" in text


async def test_analyze_tree_empty_newick_rejected():
    result = await analyze_tree.handler({"newick": ""})
    text = await text_of(result)
    assert "non-empty Newick" in text


async def test_analyze_tree_malformed_newick_reports_parse_error_not_crash():
    result = await analyze_tree.handler({"newick": "not a tree((("})
    text = await text_of(result)
    assert "Could not parse this Newick string" in text


async def test_analyze_tree_unknown_taxa_reported_gracefully():
    result = await analyze_tree.handler({"newick": SIMPLE_TREE, "taxon_a": "X", "taxon_b": "Y"})
    text = await text_of(result)
    assert "taxon/taxa not found in tree" in text
    assert "X" in text and "Y" in text


async def test_analyze_tree_only_one_taxon_given_skips_distance_without_error():
    result = await analyze_tree.handler({"newick": SIMPLE_TREE, "taxon_a": "A"})
    text = await text_of(result)
    assert "4 taxa" in text
    assert "Patristic distance" not in text


# -- compute_tree_statistics --


async def test_compute_statistics_single_tree_real_treeness():
    result = await compute_tree_statistics.handler({"newick": SIMPLE_TREE})
    text = await text_of(result)
    assert "[phykit:statistic]" in text
    assert "Treeness" in text
    assert "Robinson-Foulds" not in text


async def test_compute_statistics_self_comparison_gives_zero_rf_distance():
    result = await compute_tree_statistics.handler({"newick": SIMPLE_TREE, "newick_compare": SIMPLE_TREE})
    text = await text_of(result)
    assert "Robinson-Foulds distance to comparison tree" in text
    assert '"plain_rf": 0' in text


async def test_compute_statistics_different_topology_gives_nonzero_rf_distance():
    different_topology = "((A:0.1,C:0.1):0.1,B:0.1,D:0.1);"
    result = await compute_tree_statistics.handler({"newick": SIMPLE_TREE, "newick_compare": different_topology})
    text = await text_of(result)
    assert "Robinson-Foulds distance to comparison tree" in text
    assert '"plain_rf": 0' not in text


async def test_compute_statistics_empty_newick_rejected():
    result = await compute_tree_statistics.handler({"newick": ""})
    text = await text_of(result)
    assert "non-empty Newick" in text


async def test_compute_statistics_malformed_newick_reports_failure_not_crash():
    result = await compute_tree_statistics.handler({"newick": "garbage(((("})
    text = await text_of(result)
    assert "PhyKIT treeness failed" in text
