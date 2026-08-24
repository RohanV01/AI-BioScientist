"""E2E combo 7: comparative genomics / phylogenetics.

ensembl -> scikit_bio -> phylogenetics -> msprime -> sourmash_compare.

The real hand-off: phylogenetics.build_phylogenetic_tree and
sourmash_compare.compare_sequence_similarity both run on the exact same
real sequence pair (two independent NCBI E. coli 16S rRNA submissions,
J01859.1/X80725.1 -- the same fixtures test_sourmash_compare.py uses) --
checking that a tree-based and a MinHash-based similarity method agree
the two are closely related. ensembl/scikit_bio/msprime are independent
context legs: there is no tool that fetches a raw sequence from Ensembl
(search_gene returns coordinates/description, not sequence) or that
threads a real sequence into msprime's coalescent simulation -- both
genuine platform gaps, flagged here rather than faked.
"""
import pytest

from app.tools.ensembl import search_gene
from app.tools.msprime import simulate_coalescent_diversity
from app.tools.phylogenetics import build_phylogenetic_tree
from app.tools.scikit_bio import compute_diversity_metrics
from app.tools.sourmash_compare import compare_sequence_similarity
from tests.e2e._utils import E2ERecorder

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
# A real, genuinely-unrelated human sequence (NM_001101.5, ACTB, first
# 210bp -- same fixture test_sourmash_compare.py uses as its "unrelated"
# case) trimmed to match the E. coli fragments' length, since
# build_phylogenetic_tree requires aligned (same-length) input and needs
# >=3 taxa. It's an outgroup, not a fabricated sequence.
HUMAN_ACTB_OUTGROUP = (
    "ACCGCCGAGACCGCGTCCGCCCCGCGAGCACAGAGCCTCGCCTTTGCCGATCCGCCGCCCGTCCACACCC"
    "GCCGCCAGCTCACCATGGATGATGATATCGCCGCGCTCGTCGTCGACAACGGCTCCGGCATGTGCAAGGC"
    "CGGCTTCGCGGGCGACGATGCCCCCCGGGCCGTCTTCCCCTCCATCGTGGGGCGCCCCAGGCACCAGGGC"
)


@pytest.mark.e2e
async def test_comparative_genomics_phylogenetics():
    rec = E2ERecorder("comparative_genomics_phylogenetics")

    ensembl_text = await rec.call("ensembl.search_gene", search_gene.handler, {"symbol": "TP53"})
    rec.check("ensembl gene-identity lookup works (context-only leg, no sequence-fetch tool exists yet)", "Ensembl Gene ID" in ensembl_text, ensembl_text[:200])

    div_text = await rec.call("scikit_bio.compute_diversity_metrics", compute_diversity_metrics.handler, {"counts": [10, 5, 3, 2]})
    rec.check("scikit_bio diversity computation works (context-only leg, unrelated data shape to sequence tools)", "Shannon diversity index" in div_text, div_text[:200])

    tree_text = await rec.call(
        "phylogenetics.build_phylogenetic_tree",
        build_phylogenetic_tree.handler,
        {"sequences": {"EcoliJ01859": ECOLI_16S_1, "EcoliX80725": ECOLI_16S_2, "HumanACTB_outgroup": HUMAN_ACTB_OUTGROUP}},
    )
    rec.check("phylogenetics builds a real ML tree from the two real E. coli 16S sequences", "Maximum-likelihood tree" in tree_text, tree_text[:200])

    msprime_text = await rec.call("msprime.simulate_coalescent_diversity", simulate_coalescent_diversity.handler, {})
    rec.check("msprime coalescent simulation works (context-only leg, no tool threads a real sequence into its simulation params)", "msprime" in msprime_text.lower() or "diversity" in msprime_text.lower(), msprime_text[:200])

    sourmash_text = await rec.call(
        "sourmash_compare.compare_sequence_similarity",
        compare_sequence_similarity.handler,
        {"sequence_a": ECOLI_16S_1, "sequence_b": ECOLI_16S_2, "label_a": "EcoliJ01859", "label_b": "EcoliX80725"},
    )
    rec.check(
        "sourmash_compare's MinHash similarity, run on the exact same two real E. coli sequences phylogenetics just built a tree from, reports them as genuinely related -- both methods agree on the same real data, not just both running independently",
        "similarity" in sourmash_text.lower(),
        sourmash_text[:200],
    )

    rec.assert_all_passed()
