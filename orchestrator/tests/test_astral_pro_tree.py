"""Real tests for app/tools/astral_pro_tree.py -- no mocking, runs the
real astral-pro binary (compiled from ASTER's Linux branch at Docker
build time, see Dockerfile)."""
from app.tools.astral_pro_tree import build_species_tree


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_builds_real_species_tree():
    gene_trees = [
        "((A,B),(C,D));",
        "((A,B),(C,D));",
        "((A,C),(B,D));",
        "((A,B),(C,D));",
    ]
    result = await build_species_tree.handler({"gene_trees": gene_trees})
    text = await text_of(result)
    assert "ASTRAL-Pro" in text
    assert ";" in text


async def test_too_few_gene_trees_reports_error():
    result = await build_species_tree.handler({"gene_trees": ["((A,B),(C,D));"]})
    text = await text_of(result)
    assert "at least 2" in text


async def test_invalid_newick_reports_error():
    result = await build_species_tree.handler({"gene_trees": ["((A,B),(C,D))", "((A,B),(C,D));"]})
    text = await text_of(result)
    assert "valid Newick" in text
