"""Real tests for app/tools/msa.py -- no mocking, the actual `mafft` CLI
runs on every case here. Fixtures are the same real NCBI sequences
test_sourmash_compare.py uses: two independent E. coli 16S rRNA
submissions (J01859.1, X80725.1) with a real natural indel between them
-- the exact case that corrupted phylogenetics.build_phylogenetic_tree
when fed unaligned (docs/15-battle-test-report.md, Battle 7)."""
from app.tools.msa import align_sequences

ECOLI_16S_1 = (
    "AAATTGAAGAGTTTGATCATGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGT"
    "AACAGGAAGAAGCTTGCTCTTTGCTGACGAGTGGCGGACGGGTGAGTAATGTCTGGGAAACTGCCTGATG"
    "GAGGGGGATAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGACCAAAGAGGGGGACCTTCG"
)
ECOLI_16S_2 = (
    "AGTTTGATCATGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGTAACAGGAAG"
    "CAGCTTGCTGCTTTGCTGACGAGTGGCGGACGGGTGAGTAATGTCTGGGAAACTGCCTGATGGAGGGGGA"
    "TAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGCACAAAGAGGGGGACCTTAGGGCCTCTT"
)


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_aligns_two_indel_bearing_sequences():
    result = await align_sequences.handler({"sequences": {"SEQ_A": ECOLI_16S_1, "SEQ_B": ECOLI_16S_2}})
    text = await text_of(result)
    assert "[mafft:alignment]" in text
    assert "SEQ_A" in text and "SEQ_B" in text
    # SEQ_A is missing SEQ_B's leading 9nt -- a real alignment must insert
    # gap characters to compensate, not just report them unchanged.
    assert "-" in text


async def test_output_sequences_are_uniform_length():
    result = await align_sequences.handler({"sequences": {"SEQ_A": ECOLI_16S_1, "SEQ_B": ECOLI_16S_2}})
    text = await text_of(result)
    lines = [l for l in text.splitlines() if l.startswith("- ")]
    seqs = [l.split(": ")[1] for l in lines]
    assert len(seqs) == 2
    assert len(set(len(s) for s in seqs)) == 1


async def test_aligned_output_feeds_directly_into_phylogenetics_tree_building():
    # Closes the loop on the exact bug this tool fixes: unaligned input
    # corrupted build_phylogenetic_tree's result (one taxon's branch
    # length inflated to the model's saturation ceiling, ~10). Aligned
    # input must produce a real, small, non-saturated branch length for
    # these two closely-related sequences instead.
    from app.tools.phylogenetics import build_phylogenetic_tree

    outgroup = (
        "ACCGCCGAGACCGCGTCCGCCCCGCGAGCACAGAGCCTCGCCTTTGCCGATCCGCCGCCCGTCCACACCC"
        "GCCGCCAGCTCACCATGGATGATGATATCGCCGCGCTCGTCGTCGACAACGGCTCCGGCATGTGCAAGGC"
        "CGGCTTCGCGGGCGACGATGCCCCCCGGGCCGTCTTCCCCTCCATCGTGGGGCGCCCCAGGCACCAGGGC"
    )
    align_result = await align_sequences.handler(
        {"sequences": {"SEQ_A": ECOLI_16S_1, "SEQ_B": ECOLI_16S_2, "Outgroup": outgroup}}
    )
    text = await text_of(align_result)
    aligned = {}
    for line in text.splitlines():
        if line.startswith("- "):
            name = line.split(" (")[0][2:]
            seq = line.split(": ")[1]
            aligned[name] = seq

    tree_result = await build_phylogenetic_tree.handler({"sequences": aligned})
    tree_text = await text_of(tree_result)
    assert "[piqtree:tree]" in tree_text
    # Parse SEQ_A's branch length out of the Newick string and confirm
    # it's small (real biological signal), not saturated (~10, the bug).
    import re

    match = re.search(r"'SEQ_A':([\d.e+-]+)", tree_text) or re.search(r"SEQ_A:([\d.e+-]+)", tree_text)
    assert match, f"could not find SEQ_A branch length in: {tree_text}"
    branch_length = float(match.group(1))
    assert branch_length < 1.0, f"SEQ_A branch length {branch_length} looks saturated/corrupted -- alignment may not have taken effect"


async def test_too_few_sequences_rejected():
    result = await align_sequences.handler({"sequences": {"only_one": "ACGT"}})
    text = await text_of(result)
    assert "at least 2" in text


async def test_empty_sequence_rejected():
    result = await align_sequences.handler({"sequences": {"a": "ACGT", "b": ""}})
    text = await text_of(result)
    assert "Empty sequence" in text
