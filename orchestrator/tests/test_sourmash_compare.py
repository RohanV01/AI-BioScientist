"""Real tests for app/tools/sourmash_compare.py -- no mocking, sourmash's
actual MinHash sketching runs on every case here. Fixtures are real NCBI
sequences: two independent E. coli 16S rRNA submissions (J01859.1,
X80725.1, first 400bp) as a genuinely-related pair, and a human
beta-actin mRNA fragment (NM_001101.5, first 300bp) as genuinely
unrelated."""
from app.tools.sourmash_compare import compare_sequence_similarity

ECOLI_16S_1 = (
    "AAATTGAAGAGTTTGATCATGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGT"
    "AACAGGAAGAAGCTTGCTCTTTGCTGACGAGTGGCGGACGGGTGAGTAATGTCTGGGAAACTGCCTGATG"
    "GAGGGGGATAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGACCAAAGAGGGGGACCTTCG"
    "GGCCTCTTGCCATCGGATGTGCCCAGATGGGATTAGCTAGTAGGTGGGGTAACGGCTCACCTAGGCGACG"
    "ATCCCTAGCTGGTCTGAGAGGATGACCAGCCACACTGGAACTGAGACACGGTCCAGACTCCTACGGGAGG"
    "CAGCAGTGGGGAATATTGCACAATGGGCGCAAGCCTGATGCAGCCATGCC"
)  # J01859.1, 400bp
ECOLI_16S_2 = (
    "AGTTTGATCATGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGTAACAGGAAG"
    "CAGCTTGCTGCTTTGCTGACGAGTGGCGGACGGGTGAGTAATGTCTGGGAAACTGCCTGATGGAGGGGGA"
    "TAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGCACAAAGAGGGGGACCTTAGGGCCTCTT"
    "GCCATCGGATGTGCCCAGATGGGATTAGCTAGTAGGTGGGGTAACGGCTCACCTAGGCGACGATCCCTAG"
    "CTGGTCTGAGAGGATGACCAGCAACACTGGAACTGAGACACGGTCCAGACTCCTACGGGAGGCAGCAGTG"
    "GGGAATATTGCACAATGGGCGCAAGCCTGATGCAGCCATGCNGCGTGTAT"
)  # X80725.1, 400bp -- includes a real ambiguity code (N)
HUMAN_ACTB = (
    "ACCGCCGAGACCGCGTCCGCCCCGCGAGCACAGAGCCTCGCCTTTGCCGATCCGCCGCCCGTCCACACCC"
    "GCCGCCAGCTCACCATGGATGATGATATCGCCGCGCTCGTCGTCGACAACGGCTCCGGCATGTGCAAGGC"
    "CGGCTTCGCGGGCGACGATGCCCCCCGGGCCGTCTTCCCCTCCATCGTGGGGCGCCCCAGGCACCAGGGC"
    "GTGATGGTGGGCATGGGTCAGAAGGATTCCTATGTGGGCGACGAGGCCCAGAGCAAGAGAGGCATCCTCA"
    "CCCTGAAGTACCCCATCGAG"
)  # NM_001101.5, 300bp


async def text_of(result):
    return result["content"][0]["text"]


async def test_related_sequences_show_real_positive_similarity():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1, "sequence_b": ECOLI_16S_2, "label_a": "E.coli 16S #1", "label_b": "E.coli 16S #2"}
    )
    text = await text_of(result)
    assert "[sourmash:comparison]" in text
    # Two independent E. coli 16S submissions should show substantial, but
    # not perfect, similarity (real biological near-identity).
    assert "Jaccard similarity: 0.5" in text or "Jaccard similarity: 0.6" in text


async def test_unrelated_sequences_show_zero_similarity():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1, "sequence_b": HUMAN_ACTB, "label_a": "E.coli 16S", "label_b": "human beta-actin"}
    )
    text = await text_of(result)
    assert "Jaccard similarity: 0.0000" in text
    assert "Containment of E.coli 16S in human beta-actin: 0.0000" in text


async def test_identical_sequence_against_itself_is_perfect_similarity():
    result = await compare_sequence_similarity.handler({"sequence_a": ECOLI_16S_1, "sequence_b": ECOLI_16S_1})
    text = await text_of(result)
    assert "Jaccard similarity: 1.0000" in text
    assert "Containment of sequence A in sequence B: 1.0000" in text


async def test_fasta_header_is_stripped():
    fasta = ">J01859.1 Escherichia coli 16S ribosomal RNA\n" + ECOLI_16S_1
    result = await compare_sequence_similarity.handler({"sequence_a": fasta, "sequence_b": ECOLI_16S_1})
    text = await text_of(result)
    assert "Jaccard similarity: 1.0000" in text  # header stripped -> identical to bare sequence


async def test_lowercase_sequence_normalized():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1.lower(), "sequence_b": ECOLI_16S_1}
    )
    text = await text_of(result)
    assert "Jaccard similarity: 1.0000" in text


async def test_empty_sequence_a_rejected():
    result = await compare_sequence_similarity.handler({"sequence_a": "", "sequence_b": ECOLI_16S_1})
    text = await text_of(result)
    assert "must both be non-empty" in text


async def test_non_dna_characters_rejected():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1, "sequence_b": "PEPTIDESEQUENCE" * 10}
    )
    text = await text_of(result)
    assert "must be DNA" in text


async def test_ksize_below_minimum_rejected():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1, "sequence_b": ECOLI_16S_2, "ksize": 3}
    )
    text = await text_of(result)
    assert "ksize must be between 4 and 32" in text


async def test_ksize_above_maximum_rejected():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": ECOLI_16S_1, "sequence_b": ECOLI_16S_2, "ksize": 33}
    )
    text = await text_of(result)
    assert "ksize must be between 4 and 32" in text


async def test_sequence_shorter_than_ksize_rejected():
    result = await compare_sequence_similarity.handler(
        {"sequence_a": "ACGTACGTACGT", "sequence_b": ECOLI_16S_1, "ksize": 21}
    )
    text = await text_of(result)
    assert "must be at least 21bp" in text
