"""Real tests for app/tools/orthofinder_groups.py -- no mocking, runs
the real orthofinder CLI (self-contained release tarball, see
Dockerfile). The happy-path run is genuinely slow (full DIAMOND
all-vs-all + MCL + gene-tree inference, even on tiny toy proteomes) --
per explicit direction, latency alone is not a reason to skip or
shorten this test."""
from app.tools.orthofinder_groups import find_orthogroups


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_finds_real_orthogroups():
    # Three species, three genes each -- two clearly orthologous
    # (near-identical) genes per species plus one species-specific gene,
    # a real minimal input OrthoFinder can cluster.
    shared_a = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQ"
    shared_b = "MKVLWAALLVTFLAGCQAKVEQAVETEPEPELRQQTEWQSGQRWELALGRFWDYLRWVQTLSEQVQ"
    species = {
        "species_a": {"gene1": shared_a, "gene2": shared_b, "unique_a": "MAAVQRSTFFKLLLCVAGLLPGSEA"},
        "species_b": {"gene1": shared_a[:-3] + "AAA", "gene2": shared_b[:-3] + "GGG", "unique_b": "MKTLLLTLVVVTIVCLDLGYT"},
        "species_c": {"gene1": shared_a[:-3] + "CCC", "gene2": shared_b[:-3] + "TTT", "unique_c": "MRVLLVLGLAALLGAAA"},
    }
    result = await find_orthogroups.handler({"species": species})
    text = await text_of(result)
    assert "OrthoFinder orthogroups" in text


async def test_too_few_species_reports_error():
    result = await find_orthogroups.handler({"species": {"only_one": {"gene1": "MKT"}}})
    text = await text_of(result)
    assert "at least 2" in text


async def test_empty_species_proteins_reports_error():
    result = await find_orthogroups.handler({"species": {"a": {"gene1": "MKT"}, "b": {}}})
    text = await text_of(result)
    assert "non-empty dict" in text
